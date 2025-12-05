import requests
import json
import os

def test_agent1():
    url = "http://localhost:8080"
    
    # Read source file
    source_path = "1_graph_creation/source_cbl/CBTRN01C.cbl"
    with open(source_path, "r") as f:
        content = f.read()
        
    payload = {
        "content": content,
        "filename": "CBTRN01C.cbl"
    }
    
    try:
        print(f"Sending request to {url}...")
        response = requests.post(url, json=payload, stream=True)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            metadata = {}
            lines_list = []
            
            print("--- Streaming Response ---")
            for line in response.iter_lines():
                if line:
                    try:
                        record = json.loads(line)
                        if record.get("error"):
                            print(f"Error from stream: {record['error']}")
                            continue
                            
                        rec_type = record.get("type")
                        
                        if rec_type == "metadata":
                            metadata = record
                            print(f"Received Metadata: Program {metadata['program']['program_id']}")
                        elif rec_type == "line_record":
                            lines_list.append(record)
                            # Print update for every line (or every 10th line to avoid too much spam if needed)
                            # User asked for "constant shit in terminal"
                            print(f"Processed Line {record['line_number']}: {record['line_type']}")
                            
                    except json.JSONDecodeError:
                        print(f"Failed to decode line: {line}")

            print(f"\nTotal Source Lines Received: {len(lines_list)}")
            
            # Sort lines by line_number (since threads return out of order)
            lines_list.sort(key=lambda x: x['line_number'])
            
            # Reconstruct full JSON for file saving
            # Note: record['type'] is 'line_record', but canonical schema expects just the fields.
            # We should probably strip 'type' key or just keep it. Canonical schema example didn't have 'type' as a meta field, but had 'type' as CODE/COMMENT.
            # My 'line_record' has 'line_type'. Canonical schema uses 'type'.
            # Let's normalize to canonical schema.
            
            final_lines = []
            for l in lines_list:
                final_lines.append({
                    "line_id": l['line_id'],
                    "program_id": l['program_id'],
                    "line_number": l['line_number'],
                    "content": l['content'],
                    "type": l['line_type']
                })

            full_output = {
                "program": metadata.get("program", {}),
                "source_code_lines": final_lines
            }

            # Save to file
            output_dir = "1_graph_creation/functions/agent1_ingest_lines"
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, "01_source_lines.json")
            with open(output_path, "w") as f:
                json.dump(full_output, f, indent=2)
            print(f"\nOutput saved to: {output_path}")
            
        else:
            print("Error:", response.text)
            
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_agent1()
