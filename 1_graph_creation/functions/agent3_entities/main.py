import functions_framework
from flask import Response, jsonify
import os
import json
import time
import datetime
from google import genai
from google.genai import types

# --- Initialize Gemini ---
try:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "wz-cobol-graph")
    client = genai.Client(
        vertexai=True,
        project=project_id,
    )
    # Only print if not running as main script (to avoid double logging or if desired)
    if not os.environ.get('LOCAL_RUN'):
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
def extract_entities(request):
    """
    Agent 3: Extracts Data Entities.
    Logic:
    1. Iterate Structures.
    2. LLM Extraction per Structure (No context of previous entities).
    3. Python Duplicate Check.
    4. LLM Conflict Resolution for Duplicates (Merge/Finalize).
    5. (Local Run) Save Master List to Disk immediately.
    """
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
        }
        return ('', 204, headers)
    
    try:
        # Parse Input
        request_json = request.get_json(silent=True)
        structures = []
        program_id = "UNKNOWN"
        
        if request_json:
            if isinstance(request_json, list):
                structures = request_json
            elif isinstance(request_json, dict):
                structures = request_json.get('structures', [])
                program_id = request_json.get('program_id', "UNKNOWN")
        else:
            # Try parsing ndjson or line-delimited json from data
            data = request.get_data(as_text=True)
            for line in data.splitlines():
                if line.strip():
                    try:
                        record = json.loads(line)
                        structures.append(record)
                    except:
                        pass

        if not structures:
            return (jsonify({'error': 'No structure records provided'}), 400)

        if program_id == "UNKNOWN" and structures:
             program_id = structures[0].get('program_id', "UNKNOWN")

        # 1. Get Source Lines for Annotation
        source_lines = request_json.get('source_code_lines', [])
        line_map = { line['line_number']: line for line in source_lines } if source_lines else {}
        
        is_local = os.environ.get('LOCAL_RUN') == 'true'
        # Use absolute path for output to avoid saving in root
        if is_local:
            output_dir = os.path.dirname(os.path.abspath(__file__))
            output_file = os.path.join(output_dir, "03_entities.json")
        else:
            output_file = "/tmp/03_entities.json" # Fallback for cloud env

        def generate():
            try:
                # Sort structures by line number
                structures.sort(key=lambda x: x.get('start_line', 0))
                master_entities = {} # Name -> Record
                
                # Build FULL PROGRAM context for reference
                # This allows the LLM to see all definitions and cross-reference
                full_program_context = ""
                if line_map:
                    for ln in sorted(line_map.keys()):
                        l_obj = line_map[ln]
                        content = l_obj.get('content', '')
                        line_id = l_obj.get('line_id', 'NA')
                        if content.strip():  # Skip blank lines
                            full_program_context += f"Line {ln} [{line_id}]: {content}\n"
                
                if is_local and full_program_context:
                    ts = datetime.datetime.now().strftime("%H:%M:%S")
                    print(f"[{ts}] Built FULL PROGRAM context: {len(full_program_context)} chars", flush=True)

                for i, struct in enumerate(structures):
                    name = struct.get('name', '')
                    sType = struct.get('type', '')
                    
                    if is_local:
                        ts = datetime.datetime.now().strftime("%H:%M:%S")
                        print(f"\n[{ts}] --- Processing Structure {i+1}/{len(structures)}: {name} ({sType}) ---", flush=True)
                    
                    # Reconstruct content with Line IDs if available
                    start_line = struct.get('start_line')
                    end_line = struct.get('end_line')
                    
                    structured_content = ""
                    if start_line and end_line and line_map:
                        for ln in range(start_line, end_line + 1):
                            if ln in line_map:
                                l_obj = line_map[ln]
                                # Format: Line <Num> [ID: <ID>]: <Content>
                                structured_content += f"Line {ln} [ID: {l_obj.get('line_id', 'NA')}]: {l_obj.get('content', '')}\n"
                    else:
                        structured_content = struct.get('content', '')

                    if not structured_content.strip():
                        continue

                    # 2. LLM Extraction
                    prompt_extract = f"""
                    You are analyzing COBOL structure: {name} ({sType}).
                    Program: {program_id}.
                    
                    === FULL PROGRAM (for cross-reference) ===
                    {full_program_context}
                    
                    === CURRENT STRUCTURE TO ANALYZE ===
                    {structured_content}
                    
                    Task: Extract ALL Data Entities defined OR referenced in this code block.
                    
                    Entity Types:
                    - FILE: File definitions (SELECT, FD statements)
                    - VARIABLE: Data items at all levels (01, 05, 10...49, 77) including Level 88 Condition Names
                    - COPYBOOK: COPY statements that include external copybooks (e.g., "COPY CVTRA06Y.")
                    
                    Instructions:
                    1. COPYBOOK STATEMENTS: When you see "COPY <name>." extract it as entity_type: "COPYBOOK" with the copybook name (e.g., "CVTRA06Y").
                    
                    2. DEFINED ENTITIES: For variables/files DEFINED in this code (has a PIC clause, FD, SELECT, or level number):
                       - Set definition_line_id to the line ID where it is defined.
                    
                    3. REFERENCED BUT NOT DEFINED: For variables USED in this code (e.g., in MOVE, DISPLAY, READ INTO) but NOT DEFINED here (likely from a copybook):
                       - Set definition_line_id to null.
                       - In description, note "Defined externally (likely in copybook)."
                    
                    4. DESCRIPTION: Include relevant details (PIC clause, purpose, parent record if applicable).
                    
                    IMPORTANT: Extract EVERY variable name you see, even if you don't see its definition.
                    Cross-reference with the FULL PROGRAM above to determine definition_line_id.
                    If it's not defined anywhere in the FULL PROGRAM, it's from a COPY copybook - mark with definition_line_id: null.
                    
                    EXAMPLES - Extract BOTH source and target variables:
                    - "MOVE X TO Y" → Extract X (source), Extract Y (target)
                    - "IF A = B" → Extract A, Extract B
                    - "DISPLAY X" → Extract X
                    - "READ FILE-A INTO RECORD-B" → Extract FILE-A (file), Extract RECORD-B (variable)
                    - "PERFORM PARA-X" → Extract PARA-X (paragraph reference)
                    - "COPY COPYNAME." → Extract as COPYBOOK entity with name "COPYNAME"
                    
                    Return JSON: {{ "found_entities": [ {{ "entity_name": "...", "entity_type": "FILE/VARIABLE/COPYBOOK", "definition_line_id": "..." or null, "description": "..." }} ] }}
                    """
                    
                    contents_ext = [types.Content(role="user", parts=[types.Part.from_text(text=prompt_extract)])]
                    
                    config_ext = types.GenerateContentConfig(
                        temperature=1.0, 
                        top_p=0.95,
                        max_output_tokens=65535,
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
                        },
                        thinking_config=types.ThinkingConfig(
                            thinking_level="HIGH",
                        ),
                    )
                    
                    try:
                        resp_ext = generate_with_retries(MODEL_NAME, contents_ext, config_ext)
                        found = json.loads(resp_ext.text).get('found_entities', [])
                        if is_local:
                            ts = datetime.datetime.now().strftime("%H:%M:%S")
                            print(f"[{ts}]   > Found {len(found)} potential entities.", flush=True)
                    except Exception as exc:
                        print(f"Error extracting from {name}: {exc}")
                        continue
                    
                    # 3. Python Duplicate Check & 4. LLM Resolution
                    for item in found:
                        e_name = item['entity_name']
                        norm_name = e_name.strip().upper() # Normalization for de-duplication
                        item['program_id'] = program_id
                        # Generate entity_id (integrated from loader enrichment)
                        item['entity_id'] = f"{program_id}_{e_name}"
                        
                        updated = False
                        
                        if norm_name not in master_entities:
                            # New Entity
                            master_entities[norm_name] = item
                            if is_local:
                                ts = datetime.datetime.now().strftime("%H:%M:%S")
                                print(f"[{ts}]     + New: {e_name}", flush=True)
                                print(json.dumps(item, indent=2), flush=True)
                            yield json.dumps(item) + "\n"
                            updated = True
                        else:
                            # Duplicate found - ALWAYS reconcile (smaller structures may have better insights)
                            existing = master_entities[norm_name]
                                
                            # 4. LLM Resolution for ALL duplicates
                            if is_local:
                                ts = datetime.datetime.now().strftime("%H:%M:%S")
                                is_identical = (existing == item)
                                print(f"[{ts}]     ~ Duplicate: {e_name} {'(identical data)' if is_identical else '(different data)'}. Reconciling...", flush=True)
                                
                            prompt_resolve = f"""
                            Conflict Resolution (Additive Merge).
                            
                            Entity: {e_name}
                            
                            Record A (Existing in Master): {json.dumps(existing)}
                            Record B (New Found in {name}): {json.dumps(item)}
                            
                            Context Structure: {name}
                            Code:
                            {structured_content}
                            
                            Task:
                            Generate the FINAL, most accurate definition record for this entity by MERGING Record A and Record B.
                            
                            Strict Rules:
                            1. **PRESERVE EVERYTHING**: Do not lose any valid details from Record A.
                            2. **ADD NEW INFO**: If Record B has new details (e.g., Record Key, File Status, Access Mode) that A lacks, ADD THEM to the final record.
                            3. **IMPROVE DESCRIPTION**: Combine descriptions to form a more complete picture.
                            4. **DEFINITION LINE**: If Record B has a more definitive 'definition_line_id' (e.g., from a SELECT or FD clause) than A (which might be just a usage), update it. Otherwise, keep the earliest definition.
                            5. **ATTRIBUTES**: Ensure all attributes (access mode, organization, etc.) found in EITHER record are present in the final output.
                            
                            Return JSON (The final entity record):
                            {{ "entity_name": "...", "entity_type": "...", "definition_line_id": "...", "description": "..." }}
                            """
                            
                            contents_res = [types.Content(role="user", parts=[types.Part.from_text(text=prompt_resolve)])]
                            config_res = types.GenerateContentConfig(
                                temperature=1.0,
                                top_p=0.95,
                                max_output_tokens=65535,
                                response_mime_type="application/json",
                                response_schema={
                                    "type": "OBJECT",
                                    "properties": {
                                        "entity_name": {"type": "STRING"},
                                        "entity_type": {"type": "STRING", "enum": ["FILE", "VARIABLE", "COPYBOOK"]},
                                        "definition_line_id": {"type": "STRING", "nullable": True},
                                        "description": {"type": "STRING"}
                                    },
                                    "required": ["entity_name", "entity_type"]
                                },
                                thinking_config=types.ThinkingConfig(
                                    thinking_level="HIGH",
                                ),
                            )
                            
                            try:
                                resp_res = generate_with_retries(MODEL_NAME, contents_res, config_res)
                                final_rec = json.loads(resp_res.text)
                                final_rec['program_id'] = program_id
                                # Generate entity_id (integrated from loader enrichment)
                                final_rec['entity_id'] = f"{program_id}_{final_rec['entity_name']}"
                                
                                master_entities[norm_name] = final_rec
                                if is_local:
                                    ts = datetime.datetime.now().strftime("%H:%M:%S")
                                    print(f"[{ts}]     = Resolved: {e_name}", flush=True)
                                    print(json.dumps(final_rec, indent=2), flush=True)
                                # Emit update
                                yield json.dumps(final_rec) + "\n"
                                updated = True
                            except Exception as exc:
                                print(f"Error resolving conflict for {e_name}: {exc}")
                                continue
                        
                        # SAVE MASTER LIST if updated
                        if updated and is_local:
                            try:
                                with open(output_file, 'w') as f:
                                    # Wrap in "entities" to match canonical
                                    full_content = {"entities": list(master_entities.values())}
                                    json.dump(full_content, f, indent=2)
                                    
                                    ts = datetime.datetime.now().strftime("%H:%M:%S")
                                    print(f"\n[{ts}] --- MASTER LIST STATE (Total: {len(master_entities)}) ---", flush=True)
                                    print(json.dumps(full_content, indent=2), flush=True)
                                    print("--------------------------------------------------", flush=True)
                            except Exception as e:
                                print(f"Error saving master list: {e}", flush=True)

            except Exception as e:
                print(f"Fatal Agent 3 Error: {e}")
                
        return Response(generate(), mimetype='application/x-ndjson')

    except Exception as e:
        return (jsonify({'error': str(e)}), 500)

# --- Standalone Execution ---
if __name__ == "__main__":
    class MockRequest:
        def __init__(self, json_data):
            self._json = json_data
            self.method = 'POST'
        def get_json(self, silent=False):
            return self._json
        def get_data(self, as_text=False):
            return ""

    print("--- Starting Agent 3 Standalone ---", flush=True)
    os.environ['LOCAL_RUN'] = 'true'
    
    # Paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # Assuming we are in 1_graph_creation/functions/agent3_entities/
    # But running from root, so paths might be relative to CWD
    
    # Adjust paths based on where we expect files to be relative to this script
    # If running as python 1_graph_creation/functions/agent3_entities/main.py
    # Then __file__ is .../main.py
    
    structure_path = os.path.join(base_dir, '..', 'agent2_structure', '02_structure.json')
    lines_path = os.path.join(base_dir, '..', 'agent1_ingest_lines', '01_source_lines.json')
    
    # Check if files exist
    if not os.path.exists(structure_path):
        # Fallback to canonical references if agents haven't run
        structure_path = os.path.join(base_dir, '../../canonical_references/02_structure.json')
    
    if not os.path.exists(lines_path):
        lines_path = os.path.join(base_dir, '../../canonical_references/01_source_lines.json')

    print(f"Loading Structure: {structure_path}")
    try:
        with open(structure_path, 'r') as f:
            struct_data = json.load(f)
            structures = struct_data.get('structure', [])
    except Exception as e:
        print(f"Error loading structure: {e}")
        exit(1)
        
    print(f"Loading Lines: {lines_path}")
    try:
        with open(lines_path, 'r') as f:
            lines_data = json.load(f)
            lines = lines_data.get('source_code_lines', [])
    except Exception as e:
        print(f"Error loading lines: {e}")
        lines = []

    payload = {
        "structures": structures,
        "source_code_lines": lines,
        "program_id": "UNKNOWN" # Should be in structure or derived
    }

    req = MockRequest(payload)
    resp = extract_entities(req)
    
    if resp.status_code == 200:
        print("--- Execution Started ---")
        # Consume the stream to trigger execution
        if hasattr(resp, 'response'):
            for _ in resp.response:
                pass # Output is printed/saved inside the function
        else:
            # If it returned a string/bytes directly (not a generator in this mock context?)
            # Flask Response object with generator...
            pass 
        print("\n--- Execution Complete ---")
        print(f"Master list saved to: 03_entities.json")
    else:
        print(f"Error: {resp.status_code} - {resp.get_data()}")
