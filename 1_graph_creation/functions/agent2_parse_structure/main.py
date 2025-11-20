import functions_framework
from flask import jsonify
import re
import logging
import os
import requests

logging.basicConfig(level=logging.INFO)

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
        data = request.get_json()
        program_id = data.get('program_id')
        raw_content = data.get('node', {}).get('properties', {}).get('raw_content_preview') 
        # In real flow, we might need to fetch full content again if not passed fully
        # For this scaffold, assuming 'raw_content' is passed or we fetch from GCS again.
        # Let's assume we pass the full content for simplicity in this step or fetched in prev step.
        # Wait, Agent 1 returned 'raw_content_preview'. We need the full content.
        # We'll assume the caller passes 'full_content' or we re-fetch. 
        # For the scaffold, we will handle 'content' in input.
        
        content = data.get('content', '')
        if not content:
             return (jsonify({'error': 'Missing content'}), 400, headers)

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
                logging.info(f"Forwarding Sections to Writer: {writer_url}")
                # Writer expects: program, sections, rules
                # We construct partial payload.
                # We pass 'program' with just ID to satisfy schema if needed, or just sections.
                # Looking at writer: if program: insert_or_update Programs.
                # if sections: insert_or_update CodeSections.
                writer_payload = {
                    "program": {"properties": {"program_id": program_id}}, # Minimal
                    "sections": sections,
                    "rules": [] 
                }
                requests.post(writer_url, json=writer_payload)
            except Exception as e:
                logging.error(f"Failed to call Writer: {e}")

        # 2. Fan-out to Agent 3 (Extract Rules)
        agent3_url = os.environ.get('AGENT3_URL')
        if agent3_url:
            for section in sections:
                # Only process PROCEDURE sections or PARAGRAPHS for rules
                if section['type'] == 'PARAGRAPH' or (section['type'] == 'DIVISION' and 'PROCEDURE' in section['section_name']):
                    try:
                        logging.info(f"Forwarding Section {section['section_name']} to Agent 3")
                        payload = {"section": section}
                        requests.post(agent3_url, json=payload)
                    except Exception as e:
                        logging.error(f"Failed to call Agent 3 for {section['section_name']}: {e}")

        return (jsonify(response_data), 200, headers)

    except Exception as e:
        logging.exception(f"Parse error: {e}")
        return (jsonify({'error': str(e)}), 500, headers)
