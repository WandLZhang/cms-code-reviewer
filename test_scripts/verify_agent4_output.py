import json
import os
import requests
import sys

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def main():
    # Config
    ORCHESTRATOR_URL = "https://agent4-flow-orchestrator-6mofn5ry4a-uc.a.run.app"
    
    # Paths
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    agent2_dir = os.path.join(base_dir, '1_graph_creation/functions/agent2_structure')
    agent3_dir = os.path.join(base_dir, '1_graph_creation/functions/agent3_entities')
    agent4_dir = os.path.join(base_dir, '1_graph_creation/functions/agent4_flow')

    path_01 = os.path.join(agent2_dir, '01_source_lines_enriched.json')
    path_02 = os.path.join(agent2_dir, '02_structure.json')
    path_03 = os.path.join(agent3_dir, '03_entities.json')

    print("Loading input artifacts...")
    if not os.path.exists(path_01):
        print(f"Error: {path_01} missing.")
        return

    data_01 = load_json(path_01)
    data_02 = load_json(path_02)
    data_03 = load_json(path_03)

    payload = {
        "program_id": data_01['program']['program_id'],
        "source_lines": data_01['source_code_lines'],
        "structures": data_02['structure'],
        "entities": data_03['entities']
    }

    print(f"Calling Orchestrator: {ORCHESTRATOR_URL}")
    print("This may take a minute...")
    
    try:
        # Streaming response to handle logs
        response = requests.post(ORCHESTRATOR_URL, json=payload, stream=True)
        response.raise_for_status()
        
        full_text = ""
        print("\n--- STREAM START ---")
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                chunk_str = chunk.decode('utf-8')
                print(chunk_str, end='', flush=True)
                full_text += chunk_str
        print("\n--- STREAM END ---")
        
        # Extract JSON
        if "JSON_START" in full_text:
            json_part = full_text.split("JSON_START\n")[1].split("\nJSON_END")[0]
            result = json.loads(json_part)
            
            output_path = os.path.join(agent4_dir, '04_references_and_flow.json')
            with open(output_path, 'w') as f:
                json.dump(result, f, indent=2)
            
            print(f"\nSuccess! Saved artifact to {output_path}")
            print(f"Found {len(result.get('control_flow', []))} flow edges and {len(result.get('line_references', []))} reference edges.")
        else:
            print("\nError: Could not find JSON_START marker in response.")

    except Exception as e:
        print(f"\nRequest failed: {e}")

if __name__ == '__main__':
    main()
