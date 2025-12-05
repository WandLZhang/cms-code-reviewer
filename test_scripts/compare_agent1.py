import json
import os

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def compare_agent1():
    canonical_path = "1_graph_creation/canonical_references/01_source_lines.json"
    generated_path = "1_graph_creation/functions/agent1_ingest_lines/01_source_lines.json"
    
    if not os.path.exists(generated_path):
        print(f"Error: Generated file not found at {generated_path}")
        return

    canonical = load_json(canonical_path)
    generated = load_json(generated_path)
    
    print("--- Metadata Comparison ---")
    c_prog = canonical.get("program", {})
    g_prog = generated.get("program", {})
    
    for key in ["program_id", "program_name", "file_name", "total_lines"]:
        c_val = c_prog.get(key)
        g_val = g_prog.get(key)
        if c_val == g_val:
            print(f"[MATCH] {key}: {c_val}")
        else:
            print(f"[DIFF]  {key}: Canonical={c_val}, Generated={g_val}")

    print("\n--- Line Classification Comparison ---")
    c_lines = {l['line_number']: l for l in canonical.get("source_code_lines", [])}
    g_lines = {l['line_number']: l for l in generated.get("source_code_lines", [])}
    
    common_lines = sorted(set(c_lines.keys()) & set(g_lines.keys()))
    mismatches = []
    
    for ln in common_lines:
        c_type = c_lines[ln].get("type")
        g_type = g_lines[ln].get("type")
        
        if c_type != g_type:
            mismatches.append((ln, c_type, g_type, c_lines[ln].get("content").strip()))
            
    total = len(common_lines)
    match_count = total - len(mismatches)
    accuracy = (match_count / total) * 100 if total > 0 else 0
    
    print(f"Total Lines Compared: {total}")
    print(f"Matches: {match_count}")
    print(f"Mismatches: {len(mismatches)}")
    print(f"Accuracy: {accuracy:.2f}%")
    
    if mismatches:
        print("\nSample Mismatches (First 10):")
        print(f"{'Line':<5} | {'Canonical':<10} | {'Generated':<10} | Content")
        print("-" * 60)
        for m in mismatches[:10]:
            print(f"{m[0]:<5} | {m[1]:<10} | {m[2]:<10} | {m[3]}")

if __name__ == "__main__":
    compare_agent1()
