import json
import difflib

def verify_and_fix():
    json_path = "1_graph_creation/cbtrn01c_data.json"
    cbl_path = "1_graph_creation/cbl/CBTRN01C.cbl"
    
    with open(json_path, 'r') as f:
        data = json.load(f)
        
    with open(cbl_path, 'r') as f:
        original_lines = f.readlines()
        
    # Reconstruct from JSON
    # Sort sections by start_line
    sections = sorted(data['sections'], key=lambda x: x['start_line'])
    
    # We need to map sections to the original lines to get EXACT line numbers.
    # Strategy:
    # 1. Normalize original content (strip whitespace?) No, exact match preferred.
    # 2. Find where each section content appears in the original file.
    
    original_full_text = "".join(original_lines)
    
    current_line_idx = 0
    
    print("Verifying sections against original file...")
    
    for sec in sections:
        # Normalized content for matching (ignoring leading/trailing whitespace of the block to find start)
        # Actually, section content in JSON might be slightly off in whitespace if I manually typed it.
        # Let's assume the JSON 'content' is the source of truth for what we WANT, but we want to map it to the FILE line numbers.
        # Wait, the FILE is the source of truth.
        # I should Find the section name in the file and grab the content FROM THE FILE.
        
        name = sec['name']
        
        # Find start line of this section header in original file
        # Heuristic: Look for the name (e.g. "IDENTIFICATION DIVISION." or "MAIN-PARA.")
        found_start = -1
        found_end = -1
        
        # Search from current_line_idx
        for i in range(current_line_idx, len(original_lines)):
            line = original_lines[i].strip()
            # Check for exact match of header
            # Identification Division.
            # Main-Para.
            if line.upper().startswith(name.upper()) and (line.strip().endswith('.') or name.upper() in ["DATA DIVISION", "PROCEDURE DIVISION", "ENVIRONMENT DIVISION", "IDENTIFICATION DIVISION"]):
                 found_start = i + 1 # 1-based
                 break
                 
        if found_start == -1:
             print(f"Warning: Could not find start of section {name}")
             continue
             
        # Find end of this section (start of next section)
        # Or just take content until next known section?
        # Since sections are sorted, the next section in list should be the bound.
        # But list might be incomplete? No, I made it complete.
        
        # Actually, let's just re-read the file and re-populate the 'content' and 'line numbers' of the JSON objects
        # to be 100% accurate to the file.
        pass

    # BETTER APPROACH:
    # Parse the file fresh to get exact chunks, then map the JSON logic (Rules/Links) to these chunks.
    # This ensures "Content" and "Line Numbers" are perfect.
    
    # 1. Parse File into Chunks
    real_sections = []
    current_sec = None
    
    line_num = 0
    for line in original_lines:
        line_num += 1
        stripped = line.strip()
        
        is_header = False
        header_name = ""
        header_type = ""
        
        if "DIVISION." in stripped:
             header_name = stripped.split('.')[0]
             header_type = "DIVISION"
             is_header = True
        elif "SECTION." in stripped and not stripped.startswith("*"):
             header_name = stripped.split('.')[0]
             header_type = "SECTION"
             is_header = True
        elif re.match(r'^[A-Z0-9\-]+\.$', stripped) and not stripped.startswith("*") and "DIVISION" not in stripped and "SECTION" not in stripped:
             header_name = stripped.replace('.', '')
             header_type = "PARAGRAPH"
             is_header = True
             
        if is_header:
            if current_sec:
                current_sec['end_line'] = line_num - 1
                current_sec['content'] = "".join(current_sec['lines'])
                del current_sec['lines'] # Cleanup
                real_sections.append(current_sec)
            
            current_sec = {
                "name": header_name,
                "type": header_type,
                "start_line": line_num,
                "lines": []
            }
            
        if current_sec:
            current_sec['lines'].append(line)
            
    if current_sec:
        current_sec['end_line'] = line_num
        current_sec['content'] = "".join(current_sec['lines'])
        del current_sec['lines']
        real_sections.append(current_sec)
        
    print(f"Parsed {len(real_sections)} sections from file.")
    
    # 2. Merge with JSON Data (Rules/Calls)
    # We use the 'real_sections' as the base structure, and attach rules from JSON if section names match.
    
    name_map = {s['name']: s for s in real_sections}
    
    new_sections = []
    
    for json_sec in data['sections']:
        name = json_sec['name']
        if name in name_map:
            real = name_map[name]
            # Update JSON section with real data
            json_sec['start_line'] = real['start_line']
            json_sec['end_line'] = real['end_line']
            json_sec['content'] = real['content']
            # Update section_id if needed? Keep existing logic sec_PROGRAM_NAME
            # Ensure consistent naming
            new_sections.append(json_sec)
        else:
            print(f"Warning: JSON section {name} not found in file parser.")
            # Keep it or drop it?
            # If it's not in file, it's wrong.
            pass
            
    # 3. Add any file sections that were missing in JSON?
    # The user wants COMPLETE representation.
    for real_sec in real_sections:
        # Check if covered
        covered = False
        for js in new_sections:
            if js['name'] == real_sec['name']:
                covered = True
                break
        if not covered:
            print(f"Adding missing section from file: {real_sec['name']}")
            sec_id = f"sec_{data['program']['program_id']}_{real_sec['name'].replace(' ', '_')}"
            new_entry = {
                "section_id": sec_id,
                "name": real_sec['name'],
                "type": real_sec['type'],
                "start_line": real_sec['start_line'],
                "end_line": real_sec['end_line'],
                "content": real_sec['content']
            }
            new_sections.append(new_entry)
            
    # Sort by start_line
    new_sections.sort(key=lambda x: x['start_line'])
    
    data['sections'] = new_sections
    data['program']['total_lines'] = len(original_lines)
    
    # Write back
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2)
        
    print("Updated JSON with exact file content and structure.")

import re

if __name__ == "__main__":
    verify_and_fix()
