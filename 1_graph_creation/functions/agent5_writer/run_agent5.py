import json
import os
import sys
from unittest.mock import MagicMock
from flask import Flask

# Add function dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import graph_writer

class MockRequest:
    def __init__(self, json_data):
        self._json = json_data
        self.method = 'POST'
    
    def get_json(self, silent=True):
        return self._json

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def main():
    # Paths
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
    agent2_dir = os.path.join(base_dir, '1_graph_creation/functions/agent2_structure')
    agent3_dir = os.path.join(base_dir, '1_graph_creation/functions/agent3_entities')
    agent4_dir = os.path.join(base_dir, '1_graph_creation/functions/agent4_flow')

    print("Loading artifacts...")
    # 01 (Enriched)
    path_01 = os.path.join(agent2_dir, '01_source_lines_enriched.json')
    data_01 = load_json(path_01)
    
    # 02
    path_02 = os.path.join(agent2_dir, '02_structure.json')
    data_02 = load_json(path_02)
    
    # 03
    path_03 = os.path.join(agent3_dir, '03_entities.json')
    data_03 = load_json(path_03)
    
    # 04
    path_04 = os.path.join(agent4_dir, '04_references_and_flow.json')
    data_04 = load_json(path_04)

    # Construct Payload
    program_id = data_01['program']['program_id']
    payload = {
        "program_id": program_id,
        "source_lines": data_01['source_code_lines'],
        "structures": data_02['structure'],
        "entities": data_03['entities'],
        "flow": {
            "control_flow": data_04['control_flow'],
            "line_references": data_04['line_references']
        }
    }

    print(f"Invoking Graph Writer for {program_id}...")
    req = MockRequest(payload)
    
    # Call Function with App Context
    app = Flask(__name__)
    with app.app_context():
        response = graph_writer(req)
    
    # Handle Response
    if hasattr(response, 'get_json'):
        print("Response:", response.get_json())
    else:
        # Tuple (body, status)
        print("Response:", response)

if __name__ == '__main__':
    main()
