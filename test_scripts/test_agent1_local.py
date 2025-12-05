#!/usr/bin/env python3
"""
Test Agent1 locally with CBACT02C.cbl
"""
import sys
sys.path.insert(0, '/Users/williszhang/Projects/cms-code-reviewer/1_graph_creation/functions/agent1_ingest_lines')

import json
import os

# Set project
os.environ["GOOGLE_CLOUD_PROJECT"] = "wz-cobol-graph"

# Read the COBOL file
cbl_path = "/Users/williszhang/Projects/cms-code-reviewer/1_graph_creation/source_cbl/CBACT02C.cbl"
with open(cbl_path, 'r') as f:
    file_content = f.read()

print(f"File content length: {len(file_content)} chars")
print(f"File lines: {len(file_content.splitlines())}")
print("="*60)

# Import agent1 functions
from main import generate_with_retries, classify_single_line, MODEL_NAME, client
from google.genai import types

# Step 1: Extract metadata
prompt_meta = """
Analyze this COBOL source code.
Extract the PROGRAM-ID. If not found, suggest a name based on the content or file header.

Return a JSON object with:
- "program_id": string
"""

contents_meta = [
    types.Content(
        role="user",
        parts=[
            types.Part.from_text(text=prompt_meta),
            types.Part.from_text(text=file_content) 
        ]
    )
]

config_meta = types.GenerateContentConfig(
    temperature=0.0,
    response_mime_type="application/json",
    response_schema={
        "type": "OBJECT",
        "properties": {
            "program_id": {"type": "STRING"}
        }
    }
)

print("Extracting metadata...")
response_meta = generate_with_retries(MODEL_NAME, contents_meta, config_meta)
program_id = json.loads(response_meta.text).get('program_id', 'UNKNOWN').upper()
print(f"Program ID: {program_id}")

lines = file_content.splitlines()
metadata = {
    "type": "metadata",
    "program": {
        "program_id": program_id,
        "program_name": program_id,
        "file_name": "CBACT02C.cbl",
        "total_lines": len(lines)
    }
}
print(f"\nMetadata output:")
print(json.dumps(metadata, indent=2))
print("="*60)

# Step 2: Classify ALL lines
print(f"\nClassifying ALL {len(lines)} lines...")
import concurrent.futures

results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
    future_to_index = {
        executor.submit(classify_single_line, i, lines): i 
        for i in range(len(lines))
    }
    
    for future in concurrent.futures.as_completed(future_to_index):
        idx, l_type = future.result()
        line_record = {
            "type": "line_record",
            "line_id": f"{program_id}_{idx + 1}",
            "program_id": program_id,
            "line_number": idx + 1,
            "content": lines[idx],
            "line_type": l_type
        }
        results.append(line_record)
        print(f"Line {idx+1}: {l_type} | {lines[idx]}")

# Sort results by line number
results.sort(key=lambda x: x['line_number'])

print("\n" + "="*60)
print(f"SORTED LINE RECORDS (ALL {len(results)} lines):")
print("="*60)
for r in results:
    print(json.dumps(r))

# Save full output to file
output_path = "/Users/williszhang/Projects/cms-code-reviewer/test_scripts/agent1_cbact02c_output.json"
with open(output_path, 'w') as f:
    f.write(json.dumps(metadata) + "\n")
    for r in results:
        f.write(json.dumps(r) + "\n")
print(f"\nOutput saved to: {output_path}")
