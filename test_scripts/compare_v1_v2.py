import json
import os
import sys

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def compare_entities(new_path, old_path):
    print(f"Comparing New (Generated): {new_path}")
    print(f"With Old (Baseline): {old_path}")
    
    if not os.path.exists(new_path):
        print("New file not found.")
        return
    if not os.path.exists(old_path):
        print("Old file not found.")
        return

    new_data = load_json(new_path)
    old_data = load_json(old_path)
    
    new_list = new_data.get('entities', [])
    old_list = old_data.get('entities', [])
    
    new_map = {item['entity_name']: item for item in new_list}
    old_map = {item['entity_name']: item for item in old_list}
    
    all_names = set(new_map.keys()) | set(old_map.keys())
    
    matches = 0
    mismatches = 0
    missing_in_new = 0 # Present in Old, Missing in New
    extra_in_new = 0   # Present in New, Missing in Old
    
    print("\n--- Comparison Results (New vs Old) ---")
    
    for name in sorted(all_names):
        if name in new_map and name in old_map:
            new_item = new_map[name]
            old_item = old_map[name]
            
            diffs = []
            # Compare all fields
            all_keys = set(new_item.keys()) | set(old_item.keys())
            for k in all_keys:
                v_new = new_item.get(k)
                v_old = old_item.get(k)
                if v_new != v_old:
                    diffs.append(f"{k}: '{v_old}' -> '{v_new}'")
            
            if diffs:
                print(f"[MODIFIED] {name}")
                for d in diffs:
                    print(f"  - {d}")
                mismatches += 1
            else:
                matches += 1
                
        elif name in old_map:
            print(f"[MISSING IN NEW] {name}")
            missing_in_new += 1
        else:
            print(f"[EXTRA IN NEW] {name}")
            extra_in_new += 1
            
    print("-" * 30)
    print(f"Total Unique Names: {len(all_names)}")
    print(f"Exact Matches: {matches}")
    print(f"Modified Content: {mismatches}")
    print(f"Missing in New (removed/renamed): {missing_in_new}")
    print(f"Extra in New (new/split): {extra_in_new}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # New Output from Cloud Function
    new_path = os.path.join(base_dir, '..', '1_graph_creation', 'functions', 'agent3_entities', '03_entities.json')
    # Old Output (V1)
    old_path = os.path.join(base_dir, '..', '1_graph_creation', 'functions', 'agent3_entities', '03_entities_v1.json')
    
    compare_entities(new_path, old_path)
