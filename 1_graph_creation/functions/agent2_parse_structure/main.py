import functions_framework
from flask import jsonify
import re
# import logging
import os
import requests
import time
import concurrent.futures

# logging.basicConfig(level=logging.INFO)

def process_section_with_retries(section, agent3_url, max_retries=3):
    """
    Helper to call Agent 3 with retries.
    Returns (success: bool, message: str)
    """
    delay = 1
    for attempt in range(max_retries):
        try:
            payload = {"section": section}
            response = requests.post(agent3_url, json=payload, timeout=60)
            
            if response.status_code == 200:
                return True, f"Success: {section['section_name']}"
            elif response.status_code == 429: # Rate limit
                print(f"Rate limit for {section['section_name']}, retrying in {delay}s...", flush=True)
                time.sleep(delay)
                delay *= 2 # Exponential backoff
            else:
                return False, f"Failed: {section['section_name']} Status {response.status_code}"
                
        except Exception as e:
            print(f"Exception for {section['section_name']}: {e}, retrying...", flush=True)
            time.sleep(delay)
            delay *= 2
            
    return False, f"Failed: {section['section_name']} after {max_retries} attempts"

@functions_framework.http
def parse_structure(request):
    """
    Agent 2: Parses COBOL structure into CodeSections.
    Validates line coverage.
    """
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
        print("--- Agent 2 Received Request ---", flush=True)
        data = request.get_json()
        program_id = data.get('program_id')
        print(f"Processing Program ID: {program_id}", flush=True)
        
        content = data.get('content', '')
        if not content:
             print("Error: Missing content", flush=True)
             return (jsonify({'error': 'Missing content'}), 400, headers)
             
        print(f"RECEIVED CONTENT IN AGENT 2:\n{content}", flush=True)

        lines = content.splitlines()
        total_lines = len(lines)
        
        sections = []
        current_section = None
        
        # Regex for COBOL structure
        # Matches: "       PROCEDURE DIVISION." or "       1000-MAIN-PARA."
        div_pattern = re.compile(r'^\s{6,}(.+)\s+(DIVISION|SECTION)\.$', re.IGNORECASE)
        para_pattern = re.compile(r'^\s{6,}([A-Z0-9\-]+)\.$', re.IGNORECASE)

        covered_lines = set()

        for i, line in enumerate(lines):
            line_num = i + 1
            stripped = line.strip()
            
            # Skip comments for structure but track them for coverage?
            # COBOL comment is '*' in col 7.
            if len(line) > 6 and line[6] == '*':
                covered_lines.add(line_num)
                continue
            if not stripped:
                covered_lines.add(line_num)
                continue

            # Check for Division/Section
            div_match = div_pattern.match(line)
            para_match = para_pattern.match(line)

            if div_match:
                # Close previous section
                if current_section:
                    current_section['end_line'] = line_num - 1
                    sections.append(current_section)
                
                name = div_match.group(1).strip() + " " + div_match.group(2)
                current_section = {
                    "section_id": f"{program_id}_{name.replace(' ', '_')}",
                    "section_name": name,
                    "type": "DIVISION" if "DIVISION" in name else "SECTION",
                    "start_line": line_num,
                    "content_lines": []
                }
                covered_lines.add(line_num)

            elif para_match:
                # Paragraph detection (often main business logic units)
                if current_section:
                    current_section['end_line'] = line_num - 1
                    sections.append(current_section)
                
                name = para_match.group(1).strip()
                current_section = {
                    "section_id": f"{program_id}_{name}",
                    "section_name": name,
                    "type": "PARAGRAPH",
                    "start_line": line_num,
                    "content_lines": []
                }
                covered_lines.add(line_num)
            
            else:
                # Just a code line
                if current_section:
                    current_section['content_lines'].append(line)
                    covered_lines.add(line_num)
                else:
                    # Code before any section? (e.g. ID division header might be first)
                    pass

        # Close last section
        if current_section:
            current_section['end_line'] = total_lines
            sections.append(current_section)

        # Validation: Coverage Calculation
        coverage_pct = (len(covered_lines) / total_lines) * 100 if total_lines > 0 else 0
        uncovered = []
        if coverage_pct < 100:
            for i in range(1, total_lines + 1):
                if i not in covered_lines:
                    uncovered.append(i)

        # Prepare Output
        # We return the sections (which become Nodes).
        # We also return validation status.
        
        response_data = {
            "program_id": program_id,
            "total_lines": total_lines,
            "sections_found": len(sections),
            "coverage": {
                "percentage": f"{coverage_pct:.2f}%",
                "uncovered_lines": uncovered[:20] # Limit output
            },
            "sections": sections # In real app, these would be written to Spanner
        }

        # 1. Forward to Writer (Persist Sections)
        writer_url = os.environ.get('WRITER_URL')
        if writer_url:
            try:
                print(f"Forwarding Sections to Writer: {writer_url}", flush=True)
                writer_payload = {
                    "program": {"properties": {"program_id": program_id}}, # Minimal
                    "sections": sections,
                    "rules": [] 
                }
                requests.post(writer_url, json=writer_payload, timeout=5)
            except Exception as e:
                print(f"Error: Failed to call Writer: {e}", flush=True)

        # 2. Fan-out to Agent 3 (Extract Rules) with Parallelism & Retries
        agent3_url = os.environ.get('AGENT3_URL')
        if agent3_url:
            print(f"Fan-out to Agent 3: {agent3_url}", flush=True)
            
            # Filter sections to process
            sections_to_process = [
                s for s in sections 
                if s['type'] == 'PARAGRAPH' or (s['type'] == 'DIVISION' and 'PROCEDURE' in s['section_name'])
            ]
            total_sections = len(sections_to_process)
            completed_count = 0
            
            print(f"Starting parallel processing for {total_sections} sections...", flush=True)
            
            # Use ThreadPoolExecutor for parallelism
            # Max workers can be tuned. 5-10 is reasonable for local network calls.
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                # Submit all tasks
                future_to_section = {
                    executor.submit(process_section_with_retries, section, agent3_url): section 
                    for section in sections_to_process
                }
                
                # Process as they complete
                for future in concurrent.futures.as_completed(future_to_section):
                    completed_count += 1
                    success, msg = future.result()
                    
                    # Progress Indicator
                    progress = (completed_count / total_sections) * 100
                    print(f"[{completed_count}/{total_sections} - {progress:.1f}%] {msg}", flush=True)

        print("--- Agent 2 Processing Complete ---", flush=True)
        return (jsonify(response_data), 200, headers)

    except Exception as e:
        print(f"Parse error: {e}", flush=True)
        return (jsonify({'error': str(e)}), 500, headers)
