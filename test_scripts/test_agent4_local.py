"""
Local test for Agent 4 worker - specifically testing missing structures.
"""
import json
import os
import sys

# Add the agent4 path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../1_graph_creation/functions/agent4_flow'))

from google import genai
from google.genai import types
import time

# Config
PROJECT_ID = "wz-cobol-graph"
LOCATION = "global"
MODEL_NAME = "gemini-3-pro-preview"

# Initialize client
client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

def generate_with_retries(model, contents, config, max_retries=3):
    delay = 1
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            if attempt == max_retries - 1: raise
            time.sleep(delay)
            delay *= 2

def test_structure(target_structure_id, all_source_lines, known_entities, known_paragraphs, program_id="CBTRN01C"):
    """Test a specific structure locally"""
    
    print(f"\n{'='*60}")
    print(f"Testing: {target_structure_id}")
    print(f"{'='*60}")
    
    # Filter lines for this structure
    target_lines = [
        line for line in all_source_lines 
        if line.get('structure_id') == target_structure_id
    ]
    
    if not target_lines:
        print(f"  No lines found for {target_structure_id}")
        return None
    
    print(f"  Found {len(target_lines)} lines:")
    for line in target_lines:
        print(f"    {line['line_number']}: {line['content'][:60]}")
    
    # Build context strings
    full_code_str = ""
    for line in all_source_lines:
        ln = line.get('line_number')
        content = line.get('content', '')
        full_code_str += f"{ln} | {content}\n"

    target_code_str = ""
    for line in target_lines:
        ln = line.get('line_number')
        content = line.get('content', '')
        target_code_str += f"{ln} | {content}\n"

    # Build prompt
    prompt = f"""
    You are analyzing the Control Flow and Data References for a specific COBOL structure.
    
    Program: {program_id}
    Target Structure ID: {target_structure_id}
    
    KNOWN ENTITIES (Variables/Files):
    {json.dumps(known_entities)}
    
    KNOWN PARAGRAPHS (Flow Targets):
    {json.dumps(known_paragraphs)}
    
    === FULL PROGRAM CONTEXT (For Reference) ===
    {full_code_str}
    
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

    print("\n  Calling Gemini...")
    try:
        response = generate_with_retries(MODEL_NAME, [prompt], config)
        raw_text = response.text if response and hasattr(response, 'text') else None
        
        print(f"  Response length: {len(raw_text) if raw_text else 0}")
        
        if not raw_text or raw_text.strip() == "":
            print("  [WARN] Empty response!")
            return None
        
        result = json.loads(raw_text)
        
        print(f"\n  Control Flow: {len(result.get('control_flow', []))} items")
        for cf in result.get('control_flow', []):
            print(f"    Line {cf['line_number']}: {cf['type']} -> {cf['target_structure_name']}")
        
        print(f"\n  Line References: {len(result.get('line_references', []))} items")
        for ref in result.get('line_references', []):
            print(f"    Line {ref['line_number']}: {ref['usage_type']} -> {ref['target_entity_name']}")
        
        return result
        
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None

def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    # Load data
    print("Loading input data...")
    with open(os.path.join(base_dir, '1_graph_creation/functions/agent2_structure/01_source_lines_enriched.json')) as f:
        data_01 = json.load(f)
    with open(os.path.join(base_dir, '1_graph_creation/functions/agent2_structure/02_structure.json')) as f:
        data_02 = json.load(f)
    with open(os.path.join(base_dir, '1_graph_creation/functions/agent3_entities/03_entities.json')) as f:
        data_03 = json.load(f)
    
    source_lines = data_01['source_code_lines']
    structures = data_02['structure']
    entities = data_03['entities']
    
    entity_names = [e['entity_name'] for e in entities]
    paragraph_names = [s['name'] for s in structures if s['type'] == 'PARAGRAPH']
    
    print(f"Loaded: {len(source_lines)} lines, {len(structures)} structures, {len(entities)} entities")
    
    # Test the missing structures
    missing_structures = [
        'sec_CBTRN01C_Z-ABEND-PROGRAM',  # This had issues
        'sec_CBTRN01C_AUTHOR',            # This also had issues
    ]
    
    results = {}
    for struct_id in missing_structures:
        result = test_structure(struct_id, source_lines, entity_names, paragraph_names)
        results[struct_id] = result
    
    print("\n\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for struct_id, result in results.items():
        if result:
            print(f"{struct_id}: {len(result.get('control_flow', []))} flows, {len(result.get('line_references', []))} refs")
        else:
            print(f"{struct_id}: FAILED")

if __name__ == '__main__':
    main()
