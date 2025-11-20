import functions_framework
from flask import jsonify
import os
import re
import logging
from google.cloud import storage

# --- Initialize Logging ---
logging.basicConfig(level=logging.INFO)

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
        data = request.get_json()
        if not data:
            return (jsonify({'error': 'Invalid JSON'}), 400, headers)

        gcs_uri = data.get('gcs_uri')
        content = data.get('content')
        
        file_content = ""
        filename = ""

        # 1. Read Source Code
        if gcs_uri:
            # Parse gs://bucket/path/to/file.cbl
            if not gcs_uri.startswith("gs://"):
                return (jsonify({'error': 'Invalid GCS URI'}), 400, headers)
            
            parts = gcs_uri[5:].split("/", 1)
            bucket_name = parts[0]
            blob_name = parts[1]
            
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            file_content = blob.download_as_text()
            filename = os.path.basename(blob_name)
            logging.info(f"Read {len(file_content)} bytes from {gcs_uri}")
            
        elif content:
            file_content = content
            filename = data.get('filename', 'unknown.cbl')
        else:
            return (jsonify({'error': 'Missing gcs_uri or content'}), 400, headers)

        # 2. Extract Metadata (Program ID)
        # Regex for: PROGRAM-ID. NAME.
        match = re.search(r'PROGRAM-ID\.\s+([A-Z0-9\-]+)', file_content, re.IGNORECASE)
        if match:
            program_id = match.group(1).strip().strip('.')
        else:
            program_id = filename.split('.')[0].upper()
            logging.warning(f"Could not find PROGRAM-ID in {filename}, using filename {program_id}")

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

        return (jsonify(response_data), 200, headers)

    except Exception as e:
        logging.exception(f"Ingest error: {e}")
        return (jsonify({'error': str(e)}), 500, headers)
