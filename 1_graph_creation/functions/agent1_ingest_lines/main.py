import functions_framework
from flask import Response, jsonify
import re
import os
import json
import time
import concurrent.futures
from google.cloud import storage
from google import genai
from google.genai import types

# --- Initialize Gemini ---
try:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "wz-cobol-graph")
    client = genai.Client(
        vertexai=True,
        project=project_id,
    )
    print(f"Worker: Gemini initialized for project '{project_id}'", flush=True)
except Exception as e:
    print(f"Worker: Error initializing Gemini: {e}", flush=True)
    client = None

MODEL_NAME = "gemini-3-pro-preview"

def generate_with_retries(model, contents, config, max_retries=3):
    delay = 1
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model, 
                contents=contents,
                config=config
            )
            return response
        except Exception as e:
            time.sleep(delay)
            delay *= 2
    raise Exception("Gemini generation failed after retries")

def classify_single_line(index, all_lines):
    """
    Classifies a single line using a sliding window context.
    Returns: (index, type)
    """
    target_line = all_lines[index]
    
    start = max(0, index - 25)
    end = min(len(all_lines), index + 26)
    
    context_lines = all_lines[start:end]
    
    context_str = ""
    for i, line in enumerate(context_lines):
        # Just raw context
        context_str += f"{line}\n"

    prompt = f"""
    Classify this specific COBOL line.
    
    TARGET LINE CONTENT: "{target_line}"
    
    Options: 'CODE', 'COMMENT', 'BLANK', 'DIRECTIVE'.
    
    Definitions:
    - COMMENT: Lines starting with * or / in column 7.
    - BLANK: Empty lines or whitespace only.
    - DIRECTIVE: COPY, EJECT, SKIP statements.
    - CODE: Everything else.
    
    Surrounding Context (for reference):
    {context_str}
    
    Return JSON: {{ "type": "..." }}
    """
    
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=prompt)
            ]
        )
    ]
    
    config = types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json",
        response_schema={
            "type": "OBJECT",
            "properties": {
                "type": {"type": "STRING"}
            }
        }
    )
    
    try:
        response = generate_with_retries(MODEL_NAME, contents, config)
        result_type = json.loads(response.text).get('type', 'CODE')
        return index, result_type
    except Exception as e:
        return index, "CODE" 

@functions_framework.http
def ingest_lines(request):
    """
    Agent 1: Ingests Source Code and Tokenizes into Lines.
    Returns: Streamed NDJSON.
    """
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
        }
        return ('', 204, headers)
    
    try:
        request_json = request.get_json(silent=True)
        if not request_json:
            return (jsonify({'error': 'Invalid JSON'}), 400)
            
        gcs_uri = request_json.get('gcs_uri')
        content = request_json.get('content')
        filename = request_json.get('filename', 'unknown.cbl')

        def generate():
            try:
                # 1. Read Content
                file_content = ""
                current_filename = filename
                
                if gcs_uri:
                    if not gcs_uri.startswith("gs://"):
                        yield json.dumps({'error': 'Invalid GCS URI'}) + "\n"
                        return
                    parts = gcs_uri[5:].split("/", 1)
                    storage_client = storage.Client()
                    bucket = storage_client.bucket(parts[0])
                    blob = bucket.blob(parts[1])
                    file_content = blob.download_as_text()
                    current_filename = os.path.basename(parts[1])
                elif content:
                    file_content = content
                else:
                    yield json.dumps({'error': 'Missing gcs_uri or content'}) + "\n"
                    return

                lines = file_content.splitlines()
                if not client:
                     yield json.dumps({'error': 'Gemini client not initialized'}) + "\n"
                     return

                # 2. Extract Metadata
                prompt_meta = """
                Analyze this COBOL source code.
                Extract the PROGRAM-ID. If not found, suggest a name based on the content or file header.
                
                Return a JSON object with:
                - "program_id": string
                """
                
                contents_meta = [
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=prompt_meta),
                            types.Part.from_text(text=file_content) 
                        ]
                    )
                ]
                
                config_meta = types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "program_id": {"type": "STRING"}
                        }
                    }
                )
                
                response_meta = generate_with_retries(MODEL_NAME, contents_meta, config_meta)
                program_id = json.loads(response_meta.text).get('program_id', 'UNKNOWN').upper()
                
                metadata = {
                    "type": "metadata",
                    "program": {
                        "program_id": program_id,
                        "program_name": program_id,
                        "file_name": current_filename,
                        "total_lines": len(lines)
                    }
                }
                yield json.dumps(metadata) + "\n"

                # 3. Classify Lines (Parallel)
                with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                    future_to_index = {
                        executor.submit(classify_single_line, i, lines): i 
                        for i in range(len(lines))
                    }
                    
                    for future in concurrent.futures.as_completed(future_to_index):
                        idx, l_type = future.result()
                        line_record = {
                            "type": "line_record",
                            "line_id": f"{program_id}_{idx + 1}",
                            "program_id": program_id,
                            "line_number": idx + 1,
                            "content": lines[idx],
                            "line_type": l_type
                        }
                        yield json.dumps(line_record) + "\n"

            except Exception as e:
                yield json.dumps({'error': str(e)}) + "\n"

        return Response(generate(), mimetype='application/x-ndjson')

    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
