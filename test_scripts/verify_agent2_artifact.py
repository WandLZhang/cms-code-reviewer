import os
import json

def verify_artifact():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Load Canonical Truth
    canonical_path = os.path.join(base_dir, '..', '1_graph_creation', 'canonical_references', '02_structure.json')
    print(f"Loading Canonical Truth from: {canonical_path}")
    with open(canonical_path, 'r') as f:
        canonical_data = json.load(f)
    
    canonical_structures = {s['name']: s for s in canonical_data['structure']}
    
    # 2. Load Generated Artifact
    generated_path = os.path.join(base_dir, '..', '1_graph_creation', 'functions', 'agent2_structure', '02_structure.json')
    print(f"Loading Generated Artifact from: {generated_path}")
    if not os.path.exists(generated_path):
        print("Error: Generated artifact not found.")
        return

    with open(generated_path, 'r') as f:
        generated_data = json.load(f)
        
    generated_structures = generated_data.get('structure', [])
    generated_map = {s['name']: s for s in generated_structures}
    
    print(f"Comparing {len(generated_structures)} generated items against {len(canonical_structures)} canonical items.")

    # 3. Compare
    matches = 0
    mismatches = 0
    missing = 0
    
    for name, canon in canonical_structures.items():
        if name in generated_map:
            gen = generated_map[name]
            is_match = True
            reasons = []
            
            # Key Fields
            if gen['type'] != canon['type']:
                is_match = False
                reasons.append(f"Type: Canon={canon['type']}, Gen={gen['type']}")
            
            if gen['start_line'] != canon['start_line']:
                is_match = False
                reasons.append(f"Start: Canon={canon['start_line']}, Gen={gen['start_line']}")
                
            if gen['end_line'] != canon['end_line']:
                is_match = False
                reasons.append(f"End: Canon={canon['end_line']}, Gen={gen['end_line']}")
                
            if gen['parent_structure_id'] != canon['parent_structure_id']:
                is_match = False
                reasons.append(f"Parent: Canon={canon['parent_structure_id']}, Gen={gen['parent_structure_id']}")
            
            # ID Check
            if gen['section_id'] != canon['section_id']:
                # Warning
                reasons.append(f"ID Mismatch (Warning): Canon={canon['section_id']}, Gen={gen['section_id']}")

            if is_match:
                matches += 1
            else:
                mismatches += 1
                print(f"[MISMATCH] {name}: {'; '.join(reasons)}")
        else:
            missing += 1
            print(f"[MISSING] {name}")

    print("\n--- Summary ---")
    print(f"Matches: {matches}")
    print(f"Mismatches: {mismatches}")
    print(f"Missing: {missing}")
    
    extras = [name for name in generated_map if name not in canonical_structures]
    if extras:
        print(f"Extras ({len(extras)}): {extras}")

if __name__ == "__main__":
    verify_artifact()
