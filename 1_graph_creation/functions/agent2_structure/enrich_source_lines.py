import json
import os

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def save_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def main():
    # Paths
    # Script is in 1_graph_creation/functions/agent2_structure/
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 01 from Agent 1
    agent1_dir = os.path.join(current_dir, '../agent1_ingest_lines')
    source_lines_path = os.path.join(agent1_dir, '01_source_lines.json')
    
    # 02 from Agent 2 (Current dir)
    structure_path = os.path.join(current_dir, '02_structure.json')
    
    # Output Enriched 01 to Agent 2 dir (as requested)
    output_path = os.path.join(current_dir, '01_source_lines_enriched.json')

    print(f"Loading {source_lines_path}...")
    source_lines_data = load_json(source_lines_path)
    
    print(f"Loading {structure_path}...")
    structure_data = load_json(structure_path)

    # Build Line to Structure Map (Logic from load_canonical.py)
    line_to_structure_map = {}
    
    # Sort structures to process Divisions, then Sections, then Paragraphs
    # This ensures Paragraphs overwrite broader scopes in the map
    hierarchy = {'DIVISION': 1, 'SECTION': 2, 'PARAGRAPH': 3}
    sorted_structures = sorted(structure_data['structure'], key=lambda x: hierarchy.get(x['type'], 0))

    for item in sorted_structures:
        # Map lines to this structure
        start = item['start_line']
        end = item['end_line']
        struct_id = item['section_id']
        
        for line_num in range(start, end + 1):
            line_to_structure_map[line_num] = struct_id

    # Enrich Source Lines
    print("Enriching source lines...")
    enriched_lines = []
    for line in source_lines_data['source_code_lines']:
        # Create a copy
        new_line = line.copy()
        # Add structure_id
        new_line['structure_id'] = line_to_structure_map.get(line['line_number'])
        enriched_lines.append(new_line)

    # Create Output Artifact
    output_data = {
        "program": source_lines_data['program'],
        "source_code_lines": enriched_lines
    }

    print(f"Saving to {output_path}...")
    save_json(output_path, output_data)
    print("Done.")

if __name__ == '__main__':
    main()
