import json
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.join(base_dir, '..')

struct_path = os.path.join(root_dir, '1_graph_creation/canonical_references/02_structure.json')
lines_path = os.path.join(root_dir, '1_graph_creation/canonical_references/01_source_lines.json')
output_path = os.path.join(root_dir, 'payload.json')

print(f"Reading structure from {struct_path}")
with open(struct_path, 'r') as f:
    struct_data = json.load(f)

print(f"Reading lines from {lines_path}")
with open(lines_path, 'r') as f:
    lines_data = json.load(f)

payload = {
    "structures": struct_data.get('structure', []),
    "source_lines": lines_data.get('source_code_lines', []),
    "program_id": "CBTRN01C"
}

print(f"Writing payload to {output_path}")
with open(output_path, 'w') as f:
    json.dump(payload, f)

print("Created payload.json with", len(payload['structures']), "structures and", len(payload['source_lines']), "lines.")
