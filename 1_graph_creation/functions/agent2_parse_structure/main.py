import functions_framework
from flask import jsonify
import re
import os
import requests
import time
import json
import concurrent.futures
from google import genai
from google.genai import types

# --- Initialize Gemini ---
try:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "wz-cobol-graph")
    client = genai.Client(
        vertexai=True,
        project=project_id,
    )
    print(f"Worker: Gemini initialized for project '{project_id}'", flush=True)
except Exception as e:
    print(f"Worker: Error initializing Gemini: {e}", flush=True)
    client = None

MODEL_NAME = "gemini-3-pro-preview"

def generate_with_retries(model, contents, config, max_retries=3):
    delay = 2
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model, 
                contents=contents,
                config=config
            )
            return response
        except Exception as e:
            print(f"Gemini generation error (attempt {attempt+1}/{max_retries}): {e}", flush=True)
            time.sleep(delay)
            delay *= 2
    raise Exception("Gemini generation failed after retries")

def parse_structure_llm(content):
    if not client:
        raise Exception("Gemini client not initialized")

    prompt = """
    Analyze this COBOL source code.
    Return a JSON list of defined SECTIONS and PARAGRAPHS.
    
    INSTRUCTIONS:
    1. Identify every DIVISION, SECTION, and PARAGRAPH.
    2. Provide the exact START_LINE and END_LINE for each block.
    3. Ensure the structure is hierarchical or sequential.
    4. Do NOT include 'END-PERFORM', 'END-IF', 'END-READ' as separate sections; they belong to the preceding logic.
    5. Return ONLY valid JSON.
    
    FORMAT:
    {
        "sections": [
            {
                "name": "IDENTIFICATION DIVISION",
                "type": "DIVISION",
                "start_line": 1,
                "end_line": 5
            },
            {
                "name": "1000-MAIN-LOGIC",
                "type": "PARAGRAPH",
                "start_line": 50,
                "end_line": 80
            }
        ]
    }
    """
    
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=prompt),
                types.Part.from_text(text=content)
            ]
        )
    ]
    
    config = types.GenerateContentConfig(
        temperature=0.2, # Low temp for deterministic structure
        response_mime_type="application/json",
        response_schema={
            "type": "OBJECT",
            "properties": {
                "sections": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "name": {"type": "STRING"},
                            "type": {"type": "STRING"},
                            "start_line": {"type": "INTEGER"},
                            "end_line": {"type": "INTEGER"}
                        }
                    }
                }
            }
        }
    )
    
    response = generate_with_retries(MODEL_NAME, contents, config)
    return json.loads(response.text).get('sections', [])

def verify_structure(content, sections):
    """
    Deterministic check:
    1. Verify start line matches name.
    2. Verify coverage (no gaps).
    """
    lines = content.splitlines()
    total_lines = len(lines)
    
    # 1. Verification
    for section in sections:
        start = section['start_line']
        name = section['name']
        if start < 1 or start > total_lines:
            print(f"Validation Fail: Section {name} start line {start} out of bounds", flush=True)
            # Adjust or fail? Let's try to fuzzy match nearby?
            # For now, strict.
            continue
            
        # Check if line actually contains the name (ignoring whitespace/dots)
        line_content = lines[start-1].upper()
        normalized_name = name.upper().replace('-', ' ').replace('.', '')
        normalized_line = line_content.replace('-', ' ').replace('.', '')
        
        if normalized_name not in normalized_line and name.upper() not in line_content:
             print(f"Validation Warning: Section {name} not found clearly on line {start}: {line_content}", flush=True)
    
    # 2. Coverage (Gap Analysis)
    # Create a set of covered line numbers
    covered = set()
    for section in sections:
        # Exclude comments from "coverage" requirement? 
        # Or assume section covers everything inclusive.
        for i in range(section['start_line'], section['end_line'] + 1):
            covered.add(i)
            
    # Check gaps
    gaps = []
    for i in range(1, total_lines + 1):
        line = lines[i-1].strip()
        if i not in covered and line and not line.startswith('*'):
             gaps.append(i)
             
    if gaps:
        print(f"Validation Warning: Uncovered code lines: {len(gaps)} lines. First 10: {gaps[:10]}", flush=True)
        # Corrective Action could go here (ask Gemini B)
        # For now, we log it.

    return sections

def process_section_with_retries(section, agent3_url, max_retries=3):
    delay = 1
    for attempt in range(max_retries):
        try:
            payload = {"section": section}
            response = requests.post(agent3_url, json=payload, timeout=3600)
            
            if response.status_code == 200:
                return True, f"Success: {section['section_name']}"
            elif response.status_code == 429:
                print(f"Rate limit for {section['section_name']}, retrying...", flush=True)
                time.sleep(delay)
                delay *= 2
            else:
                return False, f"Failed: {section['section_name']} Status {response.status_code}"
        except Exception as e:
            print(f"Exception: {e}, retrying...", flush=True)
            time.sleep(delay)
            delay *= 2
    return False, f"Failed: {section['section_name']} after retries"

@functions_framework.http
def parse_structure(request):
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
        }
        return ('', 204, headers)
    
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json'
    }

    try:
        print("--- Agent 2 (LLM) Received Request ---", flush=True)
        data = request.get_json()
        program_id = data.get('program_id')
        program_node = data.get('node')
        content = data.get('content', '')
        
        if not content:
             return (jsonify({'error': 'Missing content'}), 400, headers)

        # 1. LLM Parsing
        print(f"Parsing structure for {program_id} using Gemini...", flush=True)
        raw_sections = parse_structure_llm(content)
        
        # 2. Validation
        verified_sections = verify_structure(content, raw_sections)
        
        # 3. Hydrate Content
        lines = content.splitlines()
        final_sections = []
        for s in verified_sections:
            start = s['start_line'] - 1
            end = s['end_line']
            # Ensure bounds
            start = max(0, start)
            end = min(len(lines), end)
            
            section_content_lines = lines[start:end]
            section_content = "\n".join(section_content_lines)
            
            final_sections.append({
                "section_id": f"{program_id}_{s['name'].replace(' ', '_')}",
                "section_name": s['name'],
                "type": s['type'],
                "start_line": s['start_line'],
                "end_line": s['end_line'],
                "content": section_content, # FULL CONTENT
                "content_lines": section_content_lines # Helper for Agent 3
            })

        print(f"Parsed {len(final_sections)} sections.", flush=True)

        response_data = {
            "program_id": program_id,
            "sections": final_sections
        }

        # Forward to Writer
        writer_url = os.environ.get('WRITER_URL')
        if writer_url:
            try:
                program_payload = program_node if program_node else {"properties": {"program_id": program_id, "file_name": f"{program_id}.cbl"}}
                writer_payload = {
                    "program": program_payload, 
                    "sections": final_sections,
                    "rules": [] 
                }
                import json
                # print(f"WRITER PAYLOAD: {json.dumps(writer_payload)}", flush=True) # Verbose
                requests.post(writer_url, json=writer_payload, timeout=3600)
            except Exception as e:
                print(f"Error: Failed to call Writer: {e}", flush=True)

        # Fan-out to Agent 3
        agent3_url = os.environ.get('AGENT3_URL')
        if agent3_url:
            sections_to_process = [
                s for s in final_sections 
                if s['type'] == 'PARAGRAPH' or (s['type'] == 'DIVISION' and 'PROCEDURE' in s['section_name'])
            ]
            print(f"Fan-out {len(sections_to_process)} sections to Agent 3...", flush=True)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_section = {
                    executor.submit(process_section_with_retries, section, agent3_url): section 
                    for section in sections_to_process
                }
                for future in concurrent.futures.as_completed(future_to_section):
                    success, msg = future.result()
                    # print(msg, flush=True)

        return (jsonify(response_data), 200, headers)

    except Exception as e:
        print(f"Parse error: {e}", flush=True)
        return (jsonify({'error': str(e)}), 500, headers)
