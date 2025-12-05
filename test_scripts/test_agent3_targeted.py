import sys
import os
import json
import logging
from flask import Flask

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Add function dir to path so we can import main
function_dir = os.path.join(os.path.dirname(__file__), '..', '1_graph_creation', 'functions', 'agent3_entities')
sys.path.append(os.path.abspath(function_dir))

from main import entity_worker

app = Flask(__name__)

class TestPayload:
    """Helper to wrap JSON payload for Flask request object"""
    def __init__(self, json_data):
        self._json = json_data
        self.method = 'POST'
    def get_json(self, silent=False):
        return self._json
    def get_data(self, as_text=False):
        return ""

def run_targeted_test():
    print("--- STARTING TARGETED TEST (REAL LLM EXECUTION) ---")
    
    # 1. Load Input Data
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(base_dir, '..', '1_graph_creation', 'functions', 'agent2_structure', '02_structure.json')
    source_lines_file = os.path.join(base_dir, '..', '1_graph_creation', 'functions', 'agent1_ingest_lines', '01_source_lines.json')
    
    print(f"Loading structure from: {input_file}")
    with open(input_file, 'r') as f:
        data = json.load(f)
    with open(source_lines_file, 'r') as f:
        lines_data = json.load(f)

    # Filter for "FILE SECTION" where duplicate names occur
    target_structure = next((s for s in data.get('structure', []) if s.get('name') == 'FILE SECTION'), None)
    if not target_structure:
        print("Error: FILE SECTION not found.")
        return

    print(f"\n=== STEP 1: EXECUTE EXTRACTION PROMPT ===")
    print(f"Sending 'FILE SECTION' to Gemini...")
    
    payload_extract = {
        "mode": "extract",
        "program_id": "CBTRN01C",
        "structures": [target_structure],
        "source_lines": lines_data.get('source_code_lines', [])
    }
    
    extracted_entities = []
    
    with app.app_context():
        # Call Worker (Extraction Mode) - THIS CALLS GEMINI
        req = TestPayload(payload_extract)
        resp = entity_worker(req)
        
        if resp.status_code != 200:
            print(f"Extraction Failed: {resp.status_code}")
            print(resp.get_data(as_text=True))
            return

        result = json.loads(resp.get_data(as_text=True))
        extracted_entities = result.get('entities', [])
        
        print(f"Gemini found {len(extracted_entities)} entities.")
        for e in extracted_entities:
            print(f" - {e['entity_name']} ({e['entity_type']})")

    print(f"\n=== STEP 2: GROUPING (PYTHON LOGIC) ===")
    grouped = {}
    for e in extracted_entities:
        name = e['entity_name']
        if name not in grouped: grouped[name] = []
        grouped[name].append(e)
    
    duplicates = {k: v for k, v in grouped.items() if len(v) > 1}
    print(f"Found {len(duplicates)} duplicates to reconcile.")
    
    if 'FD-CUST-DATA' in duplicates:
        print("Confirmed: FD-CUST-DATA has duplicates.")
    else:
        print("Warning: FD-CUST-DATA is NOT duplicated in extraction output.")

    print(f"\n=== STEP 3: EXECUTE RECONCILIATION PROMPT ===")
    final_entities = []
    
    # Add singles
    for name, group in grouped.items():
        if len(group) == 1:
            final_entities.append(group[0])
            
    # Resolve duplicates
    with app.app_context():
        for name, candidates in duplicates.items():
            print(f"Sending {name} ({len(candidates)} candidates) to Gemini for Resolution...")
            
            payload_resolve = {
                "mode": "resolve",
                "program_id": "CBTRN01C",
                "entity_name": name,
                "candidates": candidates
            }
            
            req = TestPayload(payload_resolve)
            resp = entity_worker(req)
            
            if resp.status_code != 200:
                print(f"Resolution Failed: {resp.status_code}")
                print(resp.get_data(as_text=True))
                continue

            result = json.loads(resp.get_data(as_text=True))
            
            resolved = result.get('entities', []) # Expecting list from new logic
            if not resolved and 'entity' in result: resolved = [result['entity']]
            
            print(f" -> Gemini returned {len(resolved)} entities:")
            for r in resolved:
                print(f"    * Name: {r['entity_name']}")
                print(f"      ID: {r.get('definition_line_id')}")
                print(f"      Desc: {r.get('description', '')[:50]}...")
            
            final_entities.extend(resolved)

    print(f"\n=== FINAL RESULT VERIFICATION ===")
    cust_data_final = [e for e in final_entities if 'FD-CUST-DATA' in e['entity_name']]
    print(f"Final count for FD-CUST-DATA variants: {len(cust_data_final)}")
    for e in cust_data_final:
        print(f" - Name: {e['entity_name']}")
        print(f"   ID: {e.get('definition_line_id')}")

if __name__ == "__main__":
    run_targeted_test()
