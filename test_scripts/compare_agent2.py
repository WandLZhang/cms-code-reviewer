import sys
import os
import json
import logging
from flask import Flask, Request

# Add the function directory to sys.path
function_dir = os.path.join(os.path.dirname(__file__), '..', '1_graph_creation', 'functions', 'agent2_structure')
sys.path.append(os.path.abspath(function_dir))

from main import identify_structure

class MockRequest:
    def __init__(self, json_data):
        self._json = json_data
        self.method = 'POST'

    def get_json(self, silent=False):
        return self._json

def compare_agent2():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Load Agent 1 Output (Input for Agent 2)
    agent1_output_path = os.path.join(base_dir, '..', '1_graph_creation', 'functions', 'agent1_ingest_lines', '01_source_lines.json')
    print(f"Loading Agent 1 output from: {agent1_output_path}")
    with open(agent1_output_path, 'r') as f:
        agent1_data = json.load(f)

    # 2. Load Canonical Truth
    canonical_path = os.path.join(base_dir, '..', '1_graph_creation', 'canonical_references', '02_structure.json')
    print(f"Loading Canonical Truth from: {canonical_path}")
    with open(canonical_path, 'r') as f:
        canonical_data = json.load(f)
    
    canonical_structures = {s['name']: s for s in canonical_data['structure']}
    print(f"Canonical contains {len(canonical_structures)} structures.")

    # 3. Run Agent 2
    program_id = agent1_data.get('program', {}).get('program_id', 'UNKNOWN')
    source_lines = agent1_data.get('source_code_lines', [])
    
    payload = {
        "program_id": program_id,
        "source_code_lines": source_lines
    }
    
    print("Running Agent 2...")
    req = MockRequest(payload)
    response = identify_structure(req)
    
    if response.status_code != 200:
        print(f"Agent 2 Failed: {response.status_code}")
        return

    response_content = response.get_data(as_text=True)
    generated_structures = []
    for line in response_content.strip().split('\n'):
        if line:
            generated_structures.append(json.loads(line))
            
    generated_map = {s['name']: s for s in generated_structures}
    print(f"Agent 2 produced {len(generated_structures)} structures.")

    # 4. Compare
    print("\n--- Comparison Results ---")
    matches = 0
    mismatches = 0
    missing = 0
    
    # Check for Canonical items in Generated
    for name, canon in canonical_structures.items():
        if name in generated_map:
            gen = generated_map[name]
            # Compare key fields
            is_match = True
            reasons = []
            
            if gen['type'] != canon['type']:
                is_match = False
                reasons.append(f"Type mismatch: Expected {canon['type']}, Got {gen['type']}")
            
            if gen['start_line'] != canon['start_line']:
                is_match = False
                reasons.append(f"Start Line mismatch: Expected {canon['start_line']}, Got {gen['start_line']}")
                
            if gen['end_line'] != canon['end_line']:
                is_match = False
                reasons.append(f"End Line mismatch: Expected {canon['end_line']}, Got {gen['end_line']}")
            
            # Parent Structure ID Check
            if gen['parent_structure_id'] != canon['parent_structure_id']:
                is_match = False
                reasons.append(f"Parent ID mismatch: Expected {canon['parent_structure_id']}, Got {gen['parent_structure_id']}")

            # ID check (optional, but good to verify determinsim)
            if gen['section_id'] != canon['section_id']:
                # Warning only
                reasons.append(f"ID mismatch (Warning): Expected {canon['section_id']}, Got {gen['section_id']}")

            if is_match:
                matches += 1
                # print(f"[OK] {name}")
            else:
                mismatches += 1
                print(f"[MISMATCH] {name}: {'; '.join(reasons)}")
        else:
            missing += 1
            print(f"[MISSING] {name} not found in Agent 2 output.")

    print("\n--- Summary ---")
    print(f"Total Canonical Items: {len(canonical_structures)}")
    print(f"Matches: {matches}")
    print(f"Mismatches: {mismatches}")
    print(f"Missing: {missing}")
    
    extra_count = len(generated_structures) - (matches + mismatches) # Roughly
    if extra_count > 0:
        print(f"Agent 2 produced {extra_count} extra items (not in canonical).")
        # List a few extras
        extras = [name for name in generated_map if name not in canonical_structures]
        print(f"Extras: {extras[:5]}...")

if __name__ == "__main__":
    compare_agent2()
