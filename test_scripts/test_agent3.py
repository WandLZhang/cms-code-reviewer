import sys
import os
import json
import logging
import asyncio
from flask import Flask, Request, Response

# Setup logging to see the stream
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger()

# Add the function directory to sys.path
function_dir = os.path.join(os.path.dirname(__file__), '..', '1_graph_creation', 'functions', 'agent3_entities')
sys.path.append(os.path.abspath(function_dir))

# Import the functions
import main
from main import entity_orchestrator, entity_worker

# Setup Mock Request
class MockRequest:
    def __init__(self, json_data):
        self._json = json_data
        self.method = 'POST'

    def get_json(self, silent=False):
        return self._json
    
    def get_data(self, as_text=False):
        return ""

# Create dummy app for context
app = Flask(__name__)

# Mock the call_worker function to run in-process
async def mock_call_worker(session, url, payload, context_tag):
    # print(f"  [Mock] calling worker for {context_tag}...")
    req = MockRequest(payload)
    
    # Call the worker function directly
    # entity_worker returns a Flask Response object (jsonify)
    with app.app_context():
        resp = entity_worker(req)
        
        # Parse JSON from response
        try:
            # Flask response.get_data() returns bytes
            return json.loads(resp.get_data(as_text=True))
        except Exception as e:
            return {'error': f"Mock Call Failed: {str(e)}"}

# Apply Patch
main.call_worker = mock_call_worker

def test_agent3_orchestrator():
    # 1. Load Input Data
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(base_dir, '..', '1_graph_creation', 'functions', 'agent2_structure', '02_structure.json')
    source_lines_file = os.path.join(base_dir, '..', '1_graph_creation', 'functions', 'agent1_ingest_lines', '01_source_lines.json')
    
    if not os.path.exists(input_file):
        print(f"Error: Input file not found: {input_file}")
        return
        
    print(f"Loading structure from: {input_file}")
    with open(input_file, 'r') as f:
        data = json.load(f)
        
    print(f"Loading source lines from: {source_lines_file}")
    with open(source_lines_file, 'r') as f:
        lines_data = json.load(f)

    # Prepare Orchestrator Payload
    payload = {
        "structures": data.get('structure', []),
        "source_lines": lines_data.get('source_code_lines', []),
        "program_id": "CBTRN01C"
    }
    
    print(f"Starting Orchestrator for {len(payload['structures'])} structures...")

    # 2. Invoke Orchestrator
    req = MockRequest(payload)
    
    try:
        response = entity_orchestrator(req)
        
        # Stream output
        full_output = ""
        
        # Handle Flask Stream
        if hasattr(response, 'response') and response.response:
            iterator = response.response
        else:
            iterator = response.get_data(as_text=True).splitlines(keepends=True)

        final_json = None
        json_buffer = ""
        capturing_json = False

        for chunk in iterator:
            if isinstance(chunk, bytes):
                chunk = chunk.decode('utf-8')
            
            # Print to console (Stream)
            print(chunk, end='')
            sys.stdout.flush()
            
            # Capture JSON part
            if "JSON_START" in chunk:
                capturing_json = True
                continue
            if "JSON_END" in chunk:
                capturing_json = False
                continue
            
            if capturing_json:
                json_buffer += chunk

        # Parse Final Artifact
        if json_buffer.strip():
            try:
                final_json = json.loads(json_buffer)
                
                # Save to file
                output_dir = os.path.join(base_dir, '..', '1_graph_creation', 'functions', 'agent3_entities')
                output_path = os.path.join(output_dir, "03_entities.json")
                
                with open(output_path, "w") as f:
                    json.dump(final_json, f, indent=2)
                print(f"\n\nArtifact saved to: {output_path}")
                
            except json.JSONDecodeError as e:
                print(f"\n\nError decoding final JSON artifact: {e}")
        else:
            print("\n\nNo JSON artifact captured from stream.")

    except Exception as e:
        print(f"\nExecution Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_agent3_orchestrator()
