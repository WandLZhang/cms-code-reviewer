import json
import os
import sys

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def compare_entities(generated_path, canonical_path):
    print(f"Comparing Generated: {generated_path}")
    print(f"With Canonical: {canonical_path}")
    
    if not os.path.exists(generated_path):
        print("Generated file not found.")
        return False

    gen_data = load_json(generated_path)
    can_data = load_json(canonical_path)
    
    gen_list = gen_data.get('entities', [])
    can_list = can_data.get('entities', [])
    
    # Convert to map for easier lookup by name
    gen_map = {item['entity_name']: item for item in gen_list}
    can_map = {item['entity_name']: item for item in can_list}
    
    all_names = set(gen_map.keys()) | set(can_map.keys())
    
    matches = 0
    mismatches = 0
    missing = 0
    extra = 0
    
    print("\n--- Comparison Results ---")
    
    for name in sorted(all_names):
        if name in gen_map and name in can_map:
            gen_item = gen_map[name]
            can_item = can_map[name]
            
            # Compare fields
            diffs = []
            if gen_item.get('entity_type') != can_item.get('entity_type'):
                diffs.append(f"Type: {gen_item.get('entity_type')} != {can_item.get('entity_type')}")
            
            # Verify schema fields presence in generated item
            schema_fields = ['entity_id', 'definition_line_id', 'description']
            missing_schema_fields = [field for field in schema_fields if field not in gen_item]
            if missing_schema_fields:
                diffs.append(f"Missing schema fields: {', '.join(missing_schema_fields)}")

            if diffs:
                print(f"[MISMATCH/SCHEMA ERROR] {name}: {', '.join(diffs)}")
                mismatches += 1
            else:
                matches += 1
                
        elif name in can_map:
            print(f"[MISSING] {name} (Expected: {can_map[name]['entity_type']})")
            missing += 1
        else:
            # Check schema for extra items too
            gen_item = gen_map[name]
            schema_issues = []
            schema_fields = ['entity_id', 'definition_line_id', 'description']
            missing_schema_fields = [field for field in schema_fields if field not in gen_item]
            
            if missing_schema_fields:
                schema_issues.append(f"Missing schema fields: {', '.join(missing_schema_fields)}")
            
            extra_msg = f"[EXTRA] {name} (Found: {gen_item.get('entity_type')})"
            if schema_issues:
                extra_msg += f" - {', '.join(schema_issues)}"
            
            print(extra_msg)
            extra += 1
            
    print("-" * 30)
    print(f"Total Entities Checked: {len(all_names)}")
    print(f"Matches: {matches}")
    print(f"Mismatches: {mismatches}")
    print(f"Missing: {missing}")
    print(f"Extra: {extra}")
    
    return missing == 0 and mismatches == 0

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    gen_path = os.path.join(base_dir, '..', '1_graph_creation', 'functions', 'agent3_entities', '03_entities_v1.json')
    can_path = os.path.join(base_dir, '..', '1_graph_creation', 'canonical_references', '03_entities.json')
    
    compare_entities(gen_path, can_path)
