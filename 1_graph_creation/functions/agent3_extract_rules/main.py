import functions_framework
from flask import jsonify
from google import genai
from google.genai import types
import os
import json
# import logging
import requests
import time

# --- Initialize Logging ---
# logging.basicConfig(level=logging.INFO)

# --- Initialize Google GenAI ---
try:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "wz-cobol-graph")
    client = genai.Client(
        vertexai=True,
        project=project_id,
    )
    print(f"Worker: Gemini initialized for project '{project_id}'", flush=True)
except Exception as e:
    print(f"Worker: Error initializing Gemini: {e}", flush=True)
    # For local testing without auth, we might need to mock or handle this gracefully
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

@functions_framework.http
def extract_rules(request):
    """
    Agent 3: Extracts Business Rules from a Code Section.
    """
    # CORS
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
        section = data.get('section')
        
        if not section:
            print("Error: Missing section data", flush=True)
            return (jsonify({'error': 'Missing section data'}), 400, headers)

        section_content = "\n".join(section.get('content_lines', []))
        section_id = section.get('section_id')
        print(f"--- Agent 3 Processing Section: {section.get('section_name')} ---", flush=True)

        # If client is not available (e.g. local without creds), mock response or fail
        if not client:
             # Mock for local test without credentials if needed, or fail
             # For now, let's return a mock if env var MOCK_AI is set, else fail
             if os.environ.get('MOCK_AI'):
                 print("Using Mock AI", flush=True)
                 return (jsonify(mock_extraction(section)), 200, headers)
             # Else proceed to try and fail if no client
             print("Error: Gemini client not initialized", flush=True)
        
        # Configure Thinking Model
        system_instruction = """You are a COBOL Modernization Expert. Analyze this code section and extract BUSINESS RULES and CONTROL FLOW.
        
        INSTRUCTIONS:
        1. Identify any logic that governs business behavior (calculations, validations, flow control).
        2. Identify any DATA ENTITIES used (variables, files).
        3. Identify explicit CONTROL FLOW statements (PERFORM, CALL, GO TO).
        4. Return a JSON object with a list of rules and a list of flow targets.
        
        FORMAT:
        {
            "rules": [
                {
                    "rule_name": "Short Name",
                    "technical_condition": "IF A = B...",
                    "plain_english": "Explanation...",
                    "entities_used": ["VAR-A", "VAR-B"]
                }
            ],
            "flow_targets": [
                {
                    "target_name": "1000-PROCESS-DATA",
                    "type": "PERFORM" 
                },
                {
                    "target_name": "SUBPROG",
                    "type": "CALL"
                }
            ]
        }"""

        user_content = f"""
        CODE SECTION ({section.get('section_name')}):
        {section_content}
        """

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=user_content)
                ]
            )
        ]

        generate_content_config = types.GenerateContentConfig(
            temperature=1,
            top_p=0.95,
            max_output_tokens=65535,
            system_instruction=[types.Part.from_text(text=system_instruction)],
            thinking_config=types.ThinkingConfig(
                thinking_level="HIGH",
            ),
        )
        
        response = generate_with_retries(MODEL_NAME, contents, generate_content_config)
        
        # Parse JSON from response
        response_text = response.text.strip()
        # Remove markdown code blocks if present
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()
            
        result_data = json.loads(response_text)
        print(f"Extracted {len(result_data.get('rules', []))} rules from {section.get('section_name')}", flush=True)
        print(f"FULL EXTRACTED RULES: {json.dumps(result_data, indent=2)}", flush=True)
        
        # Enhance with metadata
        for rule in result_data.get('rules', []):
            rule['section_id'] = section_id
            # Generate a rule ID (in real app, might use UUID or hash)
            rule['rule_id'] = f"rule_{abs(hash(rule['technical_condition']))}" 

        # Forward to Agent 4 (Link Entities)
        agent4_url = os.environ.get('AGENT4_URL')
        if agent4_url:
            for rule in result_data.get('rules', []):
                try:
                    print(f"Forwarding Rule {rule['rule_name']} to Agent 4", flush=True)
                    payload = {"rule": rule}
                    requests.post(agent4_url, json=payload, timeout=30)
                except Exception as e:
                    print(f"Error: Failed to call Agent 4: {e}", flush=True)

        # Forward Flow Targets to Writer (Agent 5)
        writer_url = os.environ.get('WRITER_URL')
        flow_targets = result_data.get('flow_targets', [])
        if writer_url and flow_targets:
            try:
                print(f"Forwarding {len(flow_targets)} flow targets to Writer: {writer_url}", flush=True)
                # Transform to expected Writer format
                section_calls = []
                for target in flow_targets:
                    section_calls.append({
                        "source_section_id": section_id,
                        "target_name": target.get('target_name'),
                        "type": target.get('type')
                    })
                
                writer_payload = {"section_calls": section_calls}
                requests.post(writer_url, json=writer_payload, timeout=30)
            except Exception as e:
                print(f"Error: Failed to call Writer for flow targets: {e}", flush=True)

        return (jsonify(result_data), 200, headers)

    except Exception as e:
        print(f"Extract error: {e}", flush=True)
        return (jsonify({'error': str(e)}), 500, headers)

def mock_extraction(section):
    return {
        "rules": [
            {
                "rule_name": "Mock Rule",
                "technical_condition": "Mock Condition",
                "plain_english": f"Mock logic found in {section.get('section_name')}",
                "entities_used": ["MOCK-ENTITY"],
                "section_id": section.get('section_id'),
                "rule_id": f"rule_mock_{section.get('section_id')}"
            }
        ]
    }
