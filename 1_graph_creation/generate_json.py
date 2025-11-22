import json
import re

INPUT_FILE = '1_graph_creation/cbl/CBTRN01C.cbl'
OUTPUT_FILE = '1_graph_creation/cbtrn01c_data.json'
PROGRAM_ID = 'CBTRN01C'

def get_line_type(line):
    stripped = line.strip()
    if not stripped:
        return 'BLANK'
    if len(line) > 6 and (line[6] == '*' or line[6] == '/'):
        return 'COMMENT'
    if stripped.startswith('COPY ') or stripped.startswith('EJECT') or stripped.startswith('SKIP'):
        return 'DIRECTIVE'
    # Divisions/Sections/Paragraphs are also CODE, but structural.
    # We can differentiate them if we want, but strictly they are CODE.
    return 'CODE'

def main():
    with open(INPUT_FILE, 'r') as f:
        lines = f.readlines()
        
    source_code_lines = []
    for i, line in enumerate(lines):
        line_num = i + 1
        line_content = line.replace('\n', '')
        line_type = get_line_type(line)
        
        source_code_lines.append({
            "line_id": f"{PROGRAM_ID}_{line_num}",
            "program_id": PROGRAM_ID,
            "line_number": line_num,
            "content": line_content,
            "type": line_type
        })

    # We can keep the existing 'sections' and 'rules' if we want, 
    # but for this task "represent ... with json", I will stick to the new schema format.
    # I will create empty placeholders for the other tables for now, as requested "fill in other stuff later".
    
    data = {
        "program": {
            "program_id": PROGRAM_ID,
            "file_name": "CBTRN01C.cbl",
            "total_lines": len(lines)
        },
        "source_code_lines": source_code_lines,
        "code_structure": [], # To be filled
        "data_entities": [],
        "line_references": [],
        "control_flow": []
    }
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(data, f, indent=2)
        
    print(f"Successfully created {OUTPUT_FILE} with {len(source_code_lines)} lines.")

if __name__ == '__main__':
    main()
