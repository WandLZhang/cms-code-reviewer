import functions_framework
from flask import Request, Response, jsonify
import os
import json
import time
import asyncio
import aiohttp
import datetime
from google import genai
from google.genai import types

# --- Configuration ---
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "wz-cobol-graph")
LOCATION = os.environ.get("GOOGLE_CLOUD_REGION", "global")
MODEL_NAME = "gemini-3-pro-preview"

# Initialize Gemini Client (Shared)
try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
except Exception as e:
    print(f"Error initializing Gemini: {e}")
    client = None

# --- Helper Functions ---

def generate_with_retries(model, contents, config, max_retries=3):
    delay = 1
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as e:
            if attempt == max_retries - 1: raise
            time.sleep(delay)
            delay *= 2

# --- WORKER FUNCTION ---

@functions_framework.http
def flow_worker(request: Request):
    """
    Worker Function.
    Analyzes a specific Structure within the context of the full program.
    """
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
        }
        return ('', 204, headers)

    try:
        req_json = request.get_json(silent=True) or {}
        program_id = req_json.get('program_id', 'UNKNOWN')
        target_structure_id = req_json.get('target_structure_id')
        all_source_lines = req_json.get('source_lines', [])
        known_entities = req_json.get('entities', []) # List of names
        known_paragraphs = req_json.get('paragraphs', []) # List of names

        if not target_structure_id:
            return jsonify({'error': 'Missing target_structure_id'}), 400

        # 1. Identify the lines for the target structure
        # (The orchestrator sends full source, but we need to know what to focus on)
        # We could pass start/end line, or filter here.
        # Let's assume the Orchestrator passed the structure metadata or we derive it.
        # Actually, it's better if the Orchestrator passes the *range* or the *lines* of the structure
        # in addition to the full context?
        # User said "just send all of 01 enriched".
        # So we need to know *which* lines are the target structure.
        # We can filter `all_source_lines` where `structure_id` == `target_structure_id`.
        
        target_lines = [
            line for line in all_source_lines 
            if line.get('structure_id') == target_structure_id
        ]
        
        if not target_lines:
            # Maybe it's a structure with no lines? (e.g. wrapper division)
            return jsonify({'control_flow': [], 'line_references': []})

        # 2. Prepare Context
        # Full code representation
        full_code_str = ""
        for line in all_source_lines:
            ln = line.get('line_number')
            content = line.get('content', '')
            full_code_str += f"{ln} | {content}\n"

        # Target Code representation
        target_code_str = ""
        for line in target_lines:
            ln = line.get('line_number')
            content = line.get('content', '')
            target_code_str += f"{ln} | {content}\n"

        # 3. Prompt
        prompt = f"""
        You are analyzing the Control Flow and Data References for a specific COBOL structure.
        
        Program: {program_id}
        Target Structure ID: {target_structure_id}
        
        KNOWN ENTITIES (Variables/Files):
        {json.dumps(known_entities)}
        
        KNOWN PARAGRAPHS (Flow Targets):
        {json.dumps(known_paragraphs)}
        
        === FULL PROGRAM CONTEXT (For Reference) ===
        {full_code_str[:50000]} ... (truncated if too massive)
        
        === TARGET STRUCTURE CODE (Analyze THESE lines) ===
        {target_code_str}
        
        TASK:
        1. Identify **Control Flow**: `PERFORM`, `GO TO`, `CALL` statements.
           - Target must be in KNOWN PARAGRAPHS (for internal flow).
           - Type: 'PERFORM', 'GO_TO', 'CALL'.
        2. Identify **Line References**: Usages of KNOWN ENTITIES.
           - Usage Types:
             - 'READS': Entity value is used/read (source in MOVE, displayed, used in COMPUTE, READ file INTO record).
             - 'WRITES': Entity is written to an output file (WRITE record).
             - 'UPDATES': Entity is modified/receives data (target in MOVE, result of COMPUTE, REWRITE record).
             - 'VALIDATES': Entity is checked in a condition (IF A = 'Y', EVALUATE).
             - 'OPENS': File is opened (OPEN INPUT/OUTPUT/EXTEND file).
             - 'CLOSES': File is closed (CLOSE file).
             - 'DECLARATION': Definition (FD, 01, 05 level, SELECT).
           
           CRITICAL FILE I/O RULES:
             - OPEN INPUT/OUTPUT/EXTEND file-name → usage_type = 'OPENS' (NOT 'READS')
             - CLOSE file-name → usage_type = 'CLOSES' (NOT 'READS' or 'UPDATES')
             - READ file-name INTO variable → file usage_type = 'READS', variable = 'UPDATES'
             - WRITE record-name → record usage_type = 'WRITES'
             - REWRITE record-name → record usage_type = 'UPDATES'
        
        OUTPUT JSON:
        {{
          "control_flow": [
            {{ "line_number": <int>, "target_structure_name": "<name>", "type": "<type>" }}
          ],
          "line_references": [
            {{ "line_number": <int>, "target_entity_name": "<name>", "usage_type": "<type>" }}
          ]
        }}
        """
        
        config = types.GenerateContentConfig(
            temperature=1.0,
            top_p=0.95,
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema={
                "type": "OBJECT",
                "properties": {
                    "control_flow": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "line_number": {"type": "INTEGER"},
                                "target_structure_name": {"type": "STRING"},
                                "type": {"type": "STRING", "enum": ["PERFORM", "GO_TO", "CALL"]}
                            },
                            "required": ["line_number", "target_structure_name", "type"]
                        }
                    },
                    "line_references": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "line_number": {"type": "INTEGER"},
                                "target_entity_name": {"type": "STRING"},
                                "usage_type": {"type": "STRING", "enum": ["READS", "WRITES", "UPDATES", "VALIDATES", "OPENS", "CLOSES", "DECLARATION"]}
                            },
                            "required": ["line_number", "target_entity_name", "usage_type"]
                        }
                    }
                }
            },
            thinking_config=types.ThinkingConfig(
                thinking_level="HIGH",
            ),
        )

        response = generate_with_retries(MODEL_NAME, [prompt], config)
        result = json.loads(response.text)
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- ORCHESTRATOR FUNCTION ---

@functions_framework.http
def flow_orchestrator(request: Request):
    """
    Orchestrator.
    1. Reads inputs (Lines, Structure, Entities).
    2. Dispatches workers for each Structure.
    3. Maps Names to IDs (Paragraph Name -> Structure ID, Entity Name -> Entity ID).
    4. Returns aggregated Control Flow & References.
    """
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
        }
        return ('', 204, headers)

    req_json = request.get_json(silent=True) or {}
    
    # Inputs
    # Expecting full artifacts or lists
    structures = req_json.get('structures', []) # 02_structure.json list
    source_lines = req_json.get('source_lines', []) # 01_source_lines_enriched.json list
    entities = req_json.get('entities', []) # 03_entities.json list
    program_id = req_json.get('program_id', 'UNKNOWN')
    
    worker_url = os.environ.get('WORKER_URL', 'http://localhost:8080')

    # Prep Context Lists
    entity_names = [e['entity_name'] for e in entities]
    paragraph_names = [s['name'] for s in structures if s['type'] == 'PARAGRAPH']
    
    # Mapping Lookups (for final ID resolution)
    # Entity Name -> Entity ID
    entity_lookup = {e['entity_name']: e['entity_id'] for e in entities}
    
    # Paragraph Name -> Structure ID
    # Logic: If multiple structures have same name, this is tricky. Assuming unique names or first match.
    structure_lookup = {s['name']: s['section_id'] for s in structures}

    def stream_process():
        yield f"--- Flow Orchestrator Started for {program_id} ---\n"
        yield f"Structures: {len(structures)}, Entities: {len(entity_names)}\n"
        
        # Filter structures to process? 
        # User wanted "all sections". We iterate all structures in 02.
        # However, divisions contain sections/paragraphs.
        # If we analyze DIVISION, it includes lines of its children.
        # If we also analyze PARAGRAPH, we duplicate analysis of those lines.
        # KEY DECISION: Only analyze the *leaf* structures (Atomic units)? 
        # Or structure_id matches.
        # 01_enriched assigns `structure_id` to the *most specific* structure.
        # So we should iterate only structures that actually have lines assigned to them in `source_lines`.
        
        active_structure_ids = set(l.get('structure_id') for l in source_lines if l.get('structure_id'))
        target_structures = [s for s in structures if s['section_id'] in active_structure_ids]
        
        yield f"Targeting {len(target_structures)} structures (those containing lines).\n"
        
        all_control_flow = []
        all_line_references = []
        
        async def process_structures():
            sem = asyncio.Semaphore(20) # Concurrency limit
            
            async def bound_call(session, payload, tag):
                async with sem:
                    return await call_worker(session, worker_url, payload, tag)

            async with aiohttp.ClientSession() as session:
                tasks = []
                for struct in target_structures:
                    payload = {
                        "program_id": program_id,
                        "target_structure_id": struct['section_id'],
                        "source_lines": source_lines, # SENDING ALL
                        "entities": entity_names,
                        "paragraphs": paragraph_names
                    }
                    task = asyncio.create_task(bound_call(session, payload, f"Struct {struct['name']}"))
                    tasks.append(task)
                return await asyncio.gather(*tasks)

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(process_structures())
            loop.close()
            
            flow_counter = 0
            ref_counter = 0
            
            for res in results:
                if 'error' in res:
                    yield f"  [Error] {res['error']}\n"
                else:
                    # Post-process and aggregate
                    flows = res.get('control_flow', [])
                    refs = res.get('line_references', [])
                    
                    # Map Names back to IDs
                    for f in flows:
                        target_name = f.get('target_structure_name')
                        line_num = f.get('line_number')
                        source_line_id = f"{program_id}_{line_num}"
                        
                        target_id = structure_lookup.get(target_name)
                        if target_id:
                            all_control_flow.append({
                                "flow_id": f"flow_{source_line_id}",
                                "source_line_id": source_line_id,
                                "target_structure_id": target_id,
                                "type": f['type']
                            })
                            flow_counter += 1
                    
                    for r in refs:
                        target_name = r.get('target_entity_name')
                        line_num = r.get('line_number')
                        source_line_id = f"{program_id}_{line_num}"
                        
                        target_id = entity_lookup.get(target_name)
                        if target_id:
                            all_line_references.append({
                                "reference_id": f"ref_{source_line_id}_{target_name}",
                                "source_line_id": source_line_id,
                                "target_entity_id": target_id,
                                "usage_type": r['usage_type']
                            })
                            ref_counter += 1
            
            yield f"Aggregation Complete. Flows: {flow_counter}, Refs: {ref_counter}\n"
            
        except Exception as e:
            yield f"Fatal Error: {e}\n"
            return

        # Final Artifact
        final_artifact = {
            "control_flow": all_control_flow,
            "line_references": all_line_references
        }
        
        yield "JSON_START\n"
        yield json.dumps(final_artifact)
        yield "\nJSON_END\n"

    return Response(stream_process(), mimetype='text/plain')

async def call_worker(session, url, payload, tag):
    try:
        # Local testing mock: if URL is localhost and not running, self-call?
        # No, we assume deployed or test harness.
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                txt = await resp.text()
                return {'error': f"{tag}: {resp.status} - {txt}"}
            return await resp.json()
    except Exception as e:
        return {'error': f"{tag}: {e}"}
