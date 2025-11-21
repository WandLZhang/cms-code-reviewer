import functions_framework
from flask import jsonify
import os
import re
import logging
import requests
from google.cloud import storage

# --- Initialize Logging ---
# logging.basicConfig(level=logging.INFO)

# --- Initialize GCP Clients ---
storage_client = storage.Client()

@functions_framework.http
def ingest_source(request):
    """
    Agent 1: Ingests COBOL source code.
    Triggered by: HTTP (or GCS Event in production).
    Action: Reads file, extracts metadata, prepares 'Program' node.
    """
    # CORS Headers
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
        }
        return ('', 204, headers)
    
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json'
    }

    try:
        print(f"--- Agent 1 Received Request ---", flush=True)
        data = request.get_json()
        print(f"Data Keys: {list(data.keys())}", flush=True)
        
        if not data:
            print("Error: Invalid JSON received", flush=True)
            return (jsonify({'error': 'Invalid JSON'}), 400, headers)

        gcs_uri = data.get('gcs_uri')
        content = data.get('content')
        
        file_content = ""
        filename = ""

        # 1. Read Source Code
        if gcs_uri:
            print(f"Processing GCS URI: {gcs_uri}", flush=True)
            # Parse gs://bucket/path/to/file.cbl
            if not gcs_uri.startswith("gs://"):
                return (jsonify({'error': 'Invalid GCS URI'}), 400, headers)
            
            parts = gcs_uri[5:].split("/", 1)
            bucket_name = parts[0]
            blob_name = parts[1]
            
            print(f"Downloading from bucket: {bucket_name}, blob: {blob_name}", flush=True)
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            file_content = blob.download_as_text()
            filename = os.path.basename(blob_name)
            print(f"Read {len(file_content)} bytes from {gcs_uri}", flush=True)
            
        elif content:
            print("Processing direct content", flush=True)
            file_content = content
            filename = data.get('filename', 'unknown.cbl')
        else:
            print("Error: Missing gcs_uri or content", flush=True)
            return (jsonify({'error': 'Missing gcs_uri or content'}), 400, headers)

        # 2. Extract Metadata (Program ID)
        # Regex for: PROGRAM-ID. NAME.
        match = re.search(r'PROGRAM-ID\.\s+([A-Z0-9\-]+)', file_content, re.IGNORECASE)
        if match:
            program_id = match.group(1).strip().strip('.')
        else:
            program_id = filename.split('.')[0].upper()
            print(f"Warning: Could not find PROGRAM-ID in {filename}, using filename {program_id}", flush=True)
        print(f"Extracted Program ID: {program_id}", flush=True)

        # 3. Prepare Output (Program Node)
        # In a real flow, we might write to Spanner here. 
        # For this architecture, we return the node data for the next step or writer.
        
        program_node = {
            "node_type": "Program",
            "properties": {
                "program_id": program_id,
                "program_name": program_id,
                "file_name": filename,
                "total_lines": len(file_content.splitlines()),
                "status": "INGESTED"
            }
        }

        response_data = {
            "status": "success",
            "program_id": program_id,
            "node": program_node,
            "raw_content_preview": file_content[:100] + "..." 
        }

        # Forward to Agent 2 if configured
        agent2_url = os.environ.get('AGENT2_URL')
        if agent2_url:
            try:
                print(f"Forwarding to Agent 2: {agent2_url}", flush=True)
                # Agent 2 expects content and program_id/node
                payload = {
                    "program_id": program_id,
                    "node": program_node,
                    "content": file_content
                }
                print(f"Payload for Agent 2 prepared. Program ID: {program_id}, Content length: {len(file_content)}", flush=True)
                response = requests.post(agent2_url, json=payload, timeout=5)
                print(f"Agent 2 responded with status: {response.status_code}", flush=True)
            except requests.exceptions.ConnectionError:
                 print(f"Error: Failed to connect to Agent 2 at {agent2_url}. Is it running?", flush=True)
            except Exception as e:
                print(f"Error: Failed to call Agent 2: {e}", flush=True)
        else:
            print("AGENT2_URL not set, skipping forwarding.", flush=True)

        print("--- Agent 1 Processing Complete ---", flush=True)
        return (jsonify(response_data), 200, headers)

    except Exception as e:
        print(f"Ingest error: {e}", flush=True)
        return (jsonify({'error': str(e)}), 500, headers)
