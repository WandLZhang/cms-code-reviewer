import sys
import os
import json
import logging
from flask import Flask, Request

# Add the function directory to sys.path
function_dir = os.path.join(os.path.dirname(__file__), '..', '1_graph_creation', 'functions', 'agent2_structure')
sys.path.append(os.path.abspath(function_dir))

# Import the function
from main import identify_structure

# Setup Mock Request
class MockRequest:
    def __init__(self, json_data):
        self._json = json_data
        self.method = 'POST'

    def get_json(self, silent=False):
        return self._json

def test_agent2():
    # 1. Load Input Data (Simulating Agent 1 Output)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # Update to use the correct ground truth file provided by user/environment
    input_file = os.path.join(base_dir, '..', '1_graph_creation', 'functions', 'agent1_ingest_lines', '01_source_lines.json')
    
    print(f"Loading input from: {input_file}")
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    # Prepare Payload
    # Agent 2 expects 'program_id' and 'source_code_lines'
    # The canonical JSON has 'program' object and 'source_code_lines' list
    program_id = data.get('program', {}).get('program_id', 'UNKNOWN')
    source_lines = data.get('source_code_lines', [])
    
    payload = {
        "program_id": program_id,
        "source_code_lines": source_lines
    }
    
    print(f"Payload prepared for Program: {program_id} with {len(source_lines)} lines.")

    # 2. Invoke Agent 2
    req = MockRequest(payload)
    
    print("\n--- Invoking Agent 2 ---")
    try:
        response = identify_structure(req)
        
        print(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            print("Response Data (NDJSON Stream):")
            # Parse NDJSON
            response_content = response.get_data(as_text=True)
            lines = response_content.strip().split('\n')
            structures = []
            for i, line in enumerate(lines):
                if not line: continue
                try:
                    record = json.loads(line)
                    structures.append(record)
                    print(f"[{i+1}] {record.get('type')} | {record.get('name')} (Lines: {record.get('start_line')}-{record.get('end_line')})")
                    if i < 3: # Print full detail for first few
                        print(json.dumps(record, indent=2))
                except json.JSONDecodeError:
                    print(f"[{i+1}] ERROR DECODING JSON: {line}")
            
            # Save to file
            output_dir = os.path.join(base_dir, '..', '1_graph_creation', 'functions', 'agent2_structure')
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, "02_structure.json")
            
            # Wrap in "structure" list
            final_output = {"structure": structures}
            
            with open(output_path, "w") as f:
                json.dump(final_output, f, indent=2)
            print(f"\nOutput saved to: {output_path}")

        else:
            print(f"Error: {response.get_data(as_text=True)}")
            
    except Exception as e:
        print(f"Execution Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_agent2()
