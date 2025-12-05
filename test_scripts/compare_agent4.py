import json
import os

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def compare_lists(canonical, generated, key_field, name="Items"):
    print(f"\n--- Comparing {name} ---")
    print(f"Canonical Count: {len(canonical)}")
    print(f"Generated Count: {len(generated)}")
    
    # Set of IDs
    canon_ids = set(item[key_field] for item in canonical)
    gen_ids = set(item[key_field] for item in generated)
    
    missing = canon_ids - gen_ids
    extra = gen_ids - canon_ids
    
    print(f"Missing IDs (in Canonical but not Generated): {len(missing)}")
    if missing:
        print(f"Sample Missing: {list(missing)[:5]}")
        
    print(f"Extra IDs (in Generated but not Canonical): {len(extra)}")
    if extra:
        print(f"Sample Extra: {list(extra)[:5]}")

    # Content comparison for intersection
    common = canon_ids.intersection(gen_ids)
    print(f"Common IDs: {len(common)}")
    
    # Check field consistency
    mismatches = []
    for uid in common:
        c_item = next(i for i in canonical if i[key_field] == uid)
        g_item = next(i for i in generated if i[key_field] == uid)
        
        # Compare all keys present in Canonical
        diffs = []
        for k, v in c_item.items():
            if k == key_field or k.startswith('created_at'): continue
            g_val = g_item.get(k)
            if g_val != v:
                diffs.append(f"{k}: {v} vs {g_val}")
        
        if diffs:
            mismatches.append((uid, diffs))

    print(f"Mismatched Items (Content differs): {len(mismatches)}")
    if mismatches:
        print("Sample Mismatches:")
        for uid, diffs in mismatches[:5]:
            print(f"  ID {uid}: {', '.join(diffs)}")

def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    canonical_path = os.path.join(base_dir, '1_graph_creation/canonical_references/04_references_and_flow.json')
    generated_path = os.path.join(base_dir, '1_graph_creation/functions/agent4_flow/04_references_and_flow.json')
    
    if not os.path.exists(generated_path):
        print("Generated file not found.")
        return

    canon = load_json(canonical_path)
    gen = load_json(generated_path)
    
    compare_lists(canon['control_flow'], gen['control_flow'], 'flow_id', "Control Flow")
    compare_lists(canon['line_references'], gen['line_references'], 'reference_id', "Line References")

if __name__ == '__main__':
    main()
