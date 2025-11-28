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
def entity_worker(request: Request):
    """
    Worker Function. Handles two modes:
    1. 'extract': Extracts entities from a list of structures.
    2. 'resolve': Merges conflicting entity definitions.
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
        mode = req_json.get('mode', 'extract')
        program_id = req_json.get('program_id', 'UNKNOWN')

        if mode == 'extract':
            return handle_extract(req_json, program_id)
        elif mode == 'resolve':
            return handle_resolve(req_json, program_id)
        else:
            return jsonify({'error': f"Unknown mode: {mode}"}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def handle_extract(req_json, program_id):
    structures = req_json.get('structures', [])
    source_lines = req_json.get('source_lines', [])
    
    # Build line map for context
    line_map = {line['line_number']: line for line in source_lines} if source_lines else {}
    
    # Build Full Program Context (Optional: Could be passed in, or built if lines provided)
    full_program_context = ""
    if line_map:
        for ln in sorted(line_map.keys()):
            l_obj = line_map[ln]
            if l_obj.get('content', '').strip():
                full_program_context += f"Line {ln} [{l_obj.get('line_id', 'NA')}]: {l_obj.get('content', '')}\n"

    found_entities = []

    for struct in structures:
        name = struct.get('name', '')
        sType = struct.get('type', '')
        
        # Reconstruct content
        structured_content = ""
        start_line = struct.get('start_line')
        end_line = struct.get('end_line')
        if start_line and end_line and line_map:
            for ln in range(start_line, end_line + 1):
                if ln in line_map:
                    l_obj = line_map[ln]
                    structured_content += f"Line {ln} [ID: {l_obj.get('line_id', 'NA')}]: {l_obj.get('content', '')}\n"
        else:
            structured_content = struct.get('content', '')

        if not structured_content.strip():
            continue

        # Gemini Call
        prompt = f"""
        You are analyzing COBOL structure: {name} ({sType}).
        Program: {program_id}.
        
        === FULL PROGRAM CONTEXT ===
        {full_program_context[:30000]} ... (truncated if too long)
        
        === CURRENT STRUCTURE ===
        {structured_content}
        
        Task: Extract ALL Data Entities defined OR referenced in this code block.
        Include: FILE, VARIABLE, COPYBOOK.
        Set definition_line_id if defined here.
        """
        
        config = types.GenerateContentConfig(
            temperature=1.0,
            response_mime_type="application/json",
            response_schema={
                "type": "OBJECT",
                "properties": {
                    "found_entities": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "entity_name": {"type": "STRING"},
                                "entity_type": {"type": "STRING", "enum": ["FILE", "VARIABLE", "COPYBOOK"]},
                                "definition_line_id": {"type": "STRING", "nullable": True},
                                "description": {"type": "STRING"}
                            },
                            "required": ["entity_name", "entity_type"]
                        }
                    }
                }
            }
        )

        try:
            resp = generate_with_retries(MODEL_NAME, [prompt], config)
            entities = json.loads(resp.text).get('found_entities', [])
            for e in entities:
                e['program_id'] = program_id
                e['found_in_structure'] = name
            found_entities.extend(entities)
        except Exception as e:
            print(f"Error extracting structure {name}: {e}")
            # Return what we have so far or error info? 
            # We'll just skip this structure in the worker output
            pass

    return jsonify({"entities": found_entities})

def handle_resolve(req_json, program_id):
    entity_name = req_json.get('entity_name')
    candidates = req_json.get('candidates', [])
    
    if not candidates:
        return jsonify({"error": "No candidates provided"}), 400
        
    prompt = f"""
    Conflict Resolution.
    Entity: {entity_name}
    Program: {program_id}
    
    I have found multiple definitions/usages for this entity from different parts of the code:
    {json.dumps(candidates, indent=2)}
    
    Task: Analyze these candidates. 
    1. If they refer to the SAME logical entity (just seen in different places), MERGE them into a single record.
    2. If they refer to DIFFERENT entities sharing the same name (e.g. defined in different FDs, different PIC clauses), KEEP them separate.
       - Rename them to ensure uniqueness by appending the DEFINITION LINE NUMBER or STRUCTURE NAME (e.g., 'FD-CUST-DATA_L100' or 'FD-CUST-DATA_DALYTRAN').
       - Ensure the description explains why they are distinct.

    Return a LIST of resolved entities (usually length 1, but >1 if distinct).
    """
    
    config = types.GenerateContentConfig(
        temperature=0.5, # Lower temp for merging
        response_mime_type="application/json",
        response_schema={
            "type": "OBJECT",
            "properties": {
                "resolved_entities": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "entity_name": {"type": "STRING"},
                            "entity_type": {"type": "STRING", "enum": ["FILE", "VARIABLE", "COPYBOOK"]},
                            "definition_line_id": {"type": "STRING", "nullable": True},
                            "description": {"type": "STRING"}
                        },
                        "required": ["entity_name", "entity_type"]
                    }
                }
            }
        }
    )
    
    try:
        resp = generate_with_retries(MODEL_NAME, [prompt], config)
        resolved = json.loads(resp.text).get('resolved_entities', [])
        for rec in resolved:
            rec['program_id'] = program_id
            rec['entity_id'] = f"{program_id}_{rec['entity_name']}"
        return jsonify({"entities": resolved})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- ORCHESTRATOR FUNCTION ---

@functions_framework.http
def entity_orchestrator(request: Request):
    """
    Orchestrator Function.
    1. Receives full structure list.
    2. Scatters extraction tasks to Worker.
    3. Gathers results.
    4. Identifies conflicts.
    5. Scatters resolution tasks to Worker.
    6. Returns final list.
    Streams logs back to caller.
    """
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
        }
        return ('', 204, headers)

    req_json = request.get_json(silent=True) or {}
    structures = req_json.get('structures', [])
    source_lines = req_json.get('source_lines', [])
    program_id = req_json.get('program_id', 'UNKNOWN')
    
    # URL of the Worker Function (Self or separate deployment)
    # In a real deployment, this should be an env var.
    # For local test or simulation, we might need to mock or loopback.
    worker_url = os.environ.get('WORKER_URL', 'http://localhost:8080') # Default/Placeholder
    
    # chunk_size = 5 # Removed per user request: 1 call per structure
    
    def stream_process():
        yield f"--- Orchestrator Started for {program_id} ---\n"
        yield f"Input: {len(structures)} structures, {len(source_lines)} source lines.\n"
        yield f"Worker URL: {worker_url}\n"
        
        # --- PHASE 1: SCATTER (Extract) ---
        # chunks = [structures[i:i + chunk_size] for i in range(0, len(structures), chunk_size)]
        yield f"Phase 1: Extracting from {len(structures)} structures (Parallel 1:1)...\n"
        
        all_entities = []
        
        async def process_structures():
            # Limit concurrency to avoid overwhelming local OS or target
            sem = asyncio.Semaphore(50) 
            
            async def bound_call(session, url, payload, tag):
                async with sem:
                    return await call_worker(session, url, payload, tag)

            async with aiohttp.ClientSession() as session:
                tasks = []
                for i, struct in enumerate(structures):
                    payload = {
                        "mode": "extract",
                        "program_id": program_id,
                        "structures": [struct], # Single structure list
                        "source_lines": source_lines 
                    }
                    struct_name = struct.get('name', f'Struct_{i}')
                    task = asyncio.create_task(bound_call(session, worker_url, payload, f"Struct {struct_name}"))
                    tasks.append(task)
                
                return await asyncio.gather(*tasks)

        # Run Async Loop in Sync Generator
        # We need a helper to run the async function and yield results as they come?
        # Ideally, we'd use an async generator, but Flask/Functions Framework expects sync generator for simple streaming 
        # or we run the loop and collect. 
        # For "streaming logs", we can gather results but print progress?
        # True streaming from async tasks in a sync generator is tricky.
        # We will run the loop, but maybe use a callback or shared queue if we want real-time updates?
        # For simplicity in this MVP: Run all chunks, then report.
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(process_structures())
            loop.close()
            
            for res in results:
                if 'error' in res:
                    yield f"  [Error] {res['error']}\n"
                else:
                    ents = res.get('entities', [])
                    all_entities.extend(ents)
                    yield f"  [Success] Got {len(ents)} entities.\n"
                    
        except Exception as e:
            yield f"Fatal Error in Phase 1: {e}\n"
            return

        yield f"Phase 1 Complete. Total Raw Entities: {len(all_entities)}\n"
        
        # --- PHASE 2: GROUP ---
        grouped = {}
        for e in all_entities:
            norm = e['entity_name'].upper().strip()
            if norm not in grouped: grouped[norm] = []
            grouped[norm].append(e)
            
        unique_count = len([k for k, v in grouped.items() if len(v) == 1])
        conflict_count = len([k for k, v in grouped.items() if len(v) > 1])
        
        yield f"Phase 2: Grouping. {len(grouped)} unique entity names.\n"
        yield f"  Single definitions: {unique_count}\n"
        yield f"  Conflicts to resolve: {conflict_count}\n"
        
        # --- PHASE 3: RECONCILE ---
        final_list = []
        
        # Add singles directly
        for name, group in grouped.items():
            if len(group) == 1:
                final_list.append(group[0])
        
        # Resolve conflicts
        if conflict_count > 0:
            yield "Phase 3: Resolving conflicts (Parallel)...\n"
            conflicts = [(name, group) for name, group in grouped.items() if len(group) > 1]
            
            async def resolve_conflicts():
                async with aiohttp.ClientSession() as session:
                    tasks = []
                    for name, group in conflicts:
                        payload = {
                            "mode": "resolve",
                            "program_id": program_id,
                            "entity_name": name,
                            "candidates": group
                        }
                        task = asyncio.create_task(call_worker(session, worker_url, payload, f"Resolve {name}"))
                        tasks.append(task)
                    return await asyncio.gather(*tasks)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            resolution_results = loop.run_until_complete(resolve_conflicts())
            loop.close()
            
            for res in resolution_results:
                if 'error' in res:
                    yield f"  [Error] Resolution failed: {res['error']}\n"
                else:
                    # Support multiple entities returned from resolution (split)
                    ents = res.get('entities', [])
                    if not ents and 'entity' in res: # Fallback for backward compat if needed
                         ents = [res['entity']]
                    
                    final_list.extend(ents)
                    # yield f"  [Resolved] {ents[0].get('entity_name')} (+{len(ents)-1} siblings)\n"
            
            yield f"Phase 3 Complete. Resolved {len(resolution_results)} conflicts.\n"

        # --- PHASE 4: FINALIZE ---
        yield "Phase 4: Finalizing Artifact...\n"
        
        final_artifact = {
            "program_id": program_id,
            "entities": final_list,
            "metadata": {
                "total_entities": len(final_list),
                "generated_at": datetime.datetime.now().isoformat()
            }
        }
        
        yield "--- Orchestration Complete ---\n"
        yield "JSON_START\n"
        yield json.dumps(final_artifact)
        yield "\nJSON_END\n"

    return Response(stream_process(), mimetype='text/plain')

async def call_worker(session, url, payload, context_tag):
    try:
        # In local testing or if URLs are not set up, this might fail.
        # Need error handling.
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                txt = await resp.text()
                return {'error': f"{context_tag}: Status {resp.status} - {txt}"}
            return await resp.json()
    except Exception as e:
        return {'error': f"{context_tag}: {str(e)}"}

# --- Local/Main execution for testing ---
if __name__ == "__main__":
    # Mock setup to test orchestrator logic locally?
    print("Please deploy to Cloud Functions to run.")
