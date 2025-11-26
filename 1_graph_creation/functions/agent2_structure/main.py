import functions_framework
from flask import Response, jsonify
import os
import json
import time
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

@functions_framework.http
def identify_structure(request):
    """
    Agent 2: Parses Code Structure (Divisions, Sections, Paragraphs).
    Input: JSON stream from Agent 1 (metadata + line_records).
    Output: NDJSON stream of Structure Records.
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
            # If not direct JSON, try to parse NDJSON if that's what we received
            # But typically cloud functions receive a single JSON body. 
            # If this is part of a pipeline, we expect a list of objects.
            # Let's assume we receive a JSON object with "source_lines" list for now 
            # to simplify the dev loop, or we'll adapt if it's a stream.
            return (jsonify({'error': 'Invalid JSON'}), 400)
            
        # Expected input format from Agent 1 aggregator or direct call
        # { "program_id": "...", "source_code_lines": [ ... ] }
        program_id = request_json.get('program_id', 'UNKNOWN')
        lines_data = request_json.get('source_code_lines', [])
        
        if not lines_data:
             return (jsonify({'error': 'No source code lines provided'}), 400)

        def generate():
            try:
                # 1. Prepare Context for LLM
                # We only need CODE lines for structure, but comments might help context.
                # Let's provide everything but keeping it concise with line numbers.
                numbered_code = ""
                line_map = {} # line_number -> content
                
                for line in lines_data:
                    ln = line.get('line_number')
                    content = line.get('content', '')
                    l_type = line.get('type', 'CODE') # 'line_type' or 'type'
                    
                    line_map[ln] = content
                    numbered_code += f"{ln:06d} | {content}\n"

                # 2. Prompt LLM for Start Lines
                prompt = f"""
                Analyze this COBOL source code structure.
                Identify all DIVISIONS, SECTIONS, and PARAGRAPHS.
                
                Return a JSON object with a list of "structures".
                Each structure must have:
                - "name": The exact name (e.g., "IDENTIFICATION DIVISION", "MAIN-PARA").
                - "type": "DIVISION", "SECTION", or "PARAGRAPH".
                - "start_line": The distinct line number (from the provided text) where it starts.
                
                Rules:
                - Do not invent structures.
                - Capture every paragraph in the PROCEDURE DIVISION.
                - Capture File Definitions (FD) if they look like structural blocks (optional, but focus on Control Flow).
                
                CODE:
                {numbered_code}
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
                    temperature=1.0, # Thinking models often require non-zero temp, user snippet showed 1
                    top_p=0.95,
                    max_output_tokens=65535,
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "structures": {
                                "type": "ARRAY",
                                "items": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "name": {"type": "STRING"},
                                        "type": {"type": "STRING", "enum": ["DIVISION", "SECTION", "PARAGRAPH"]},
                                        "start_line": {"type": "INTEGER"}
                                    },
                                    "required": ["name", "type", "start_line"]
                                }
                            }
                        }
                    },
                    thinking_config=types.ThinkingConfig(
                        thinking_level="HIGH",
                    ),
                )
                
                response = generate_with_retries(MODEL_NAME, contents, config)
                llm_structures = json.loads(response.text).get('structures', [])
                
                # 3. Calculate Hierarchy and End Lines (Python Logic)
                # Sort by start_line to be safe
                llm_structures.sort(key=lambda x: x['start_line'])
                
                hierarchy_levels = {
                    "DIVISION": 1,
                    "SECTION": 2,
                    "PARAGRAPH": 3
                }
                
                processed_structures = []
                
                # Stack to track active parents: [(level, structure_ref)]
                # But simpler: for each structure, its end is the start of the next structure 
                # OF THE SAME OR HIGHER (lower val) LEVEL.
                
                total_lines_count = max(line_map.keys())
                
                for i, current in enumerate(llm_structures):
                    current_level = hierarchy_levels.get(current['type'], 3)
                    current_start = current['start_line']
                    
                    # Find End Line
                    # Default end is end of file
                    current_end = total_lines_count
                    
                    # Look ahead for the next structure that terminates this one
                    for next_struct in llm_structures[i+1:]:
                        next_level = hierarchy_levels.get(next_struct['type'], 3)
                        if next_level <= current_level:
                            current_end = next_struct['start_line'] - 1
                            break
                    
                    # Cap end line at total lines if it overshot (shouldn't happen with logic above but safety)
                    # Actually, if the next structure starts at X, this ends at X-1.
                    # If no next structure closes it, it goes to EOF.
                    
                    # Find Parent
                    # The parent is the closest preceding structure with level < current_level
                    parent_id = None
                    for prev in reversed(processed_structures):
                        prev_level = hierarchy_levels.get(prev['type'], 3)
                        if prev_level < current_level:
                            parent_id = prev['section_id']
                            break
                    
                    # Create Record
                    # sanitize name for ID
                    safe_name = current['name'].replace(" ", "_").upper()
                    structure_id = f"sec_{program_id}_{safe_name}"
                    
                    # Extract Content
                    # Reconstruct content from line_map for this range
                    # This is optional but requested in schema
                    chunk_content = ""
                    for ln in range(current_start, current_end + 1):
                        if ln in line_map:
                            chunk_content += line_map[ln] + "\n"

                    record = {
                        "section_id": structure_id,
                        "program_id": program_id,
                        "name": current['name'],
                        "type": current['type'],
                        "start_line": current_start,
                        "end_line": current_end,
                        "parent_structure_id": parent_id,
                        "content": chunk_content
                    }
                    
                    processed_structures.append(record)
                    yield json.dumps(record) + "\n"

            except Exception as e:
                yield json.dumps({'error': str(e)}) + "\n"

        return Response(generate(), mimetype='application/x-ndjson')

    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
