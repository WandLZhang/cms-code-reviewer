import functions_framework
from flask import jsonify
from google import genai
import os
import json
import logging

# --- Initialize Logging ---
logging.basicConfig(level=logging.INFO)

# --- Initialize Google GenAI ---
try:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "wz-cobol-graph")
    client = genai.Client(
        vertexai=True,
        project=project_id,
        location="us-central1",
    )
    logging.info(f"Worker: Gemini initialized for project '{project_id}'")
except Exception as e:
    logging.error(f"Worker: Error initializing Gemini: {e}", exc_info=True)
    # For local testing without auth, we might need to mock or handle this gracefully
    client = None

MODEL_NAME = "gemini-2.5-pro"

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
            return (jsonify({'error': 'Missing section data'}), 400, headers)

        section_content = "\n".join(section.get('content_lines', []))
        section_id = section.get('section_id')

        # If client is not available (e.g. local without creds), mock response or fail
        if not client:
             # Mock for local test without credentials if needed, or fail
             # For now, let's return a mock if env var MOCK_AI is set, else fail
             if os.environ.get('MOCK_AI'):
                 return (jsonify(mock_extraction(section)), 200, headers)
             # Else proceed to try and fail if no client
        
        prompt = f"""
        You are a COBOL Modernization Expert. Analyze this code section and extract BUSINESS RULES.
        
        CODE SECTION ({section.get('section_name')}):
        {section_content}
        
        INSTRUCTIONS:
        1. Identify any logic that governs business behavior (calculations, validations, flow control).
        2. Identify any DATA ENTITIES used (variables, files).
        3. Return a JSON object with a list of rules.
        
        FORMAT:
        {{
            "rules": [
                {{
                    "rule_name": "Short Name",
                    "technical_condition": "IF A = B...",
                    "plain_english": "Explanation...",
                    "entities_used": ["VAR-A", "VAR-B"]
                }}
            ]
        }}
        """
        
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        
        # Parse JSON from response
        response_text = response.text.strip()
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()
            
        result_data = json.loads(response_text)
        
        # Enhance with metadata
        for rule in result_data.get('rules', []):
            rule['section_id'] = section_id
            # Generate a rule ID (in real app, might use UUID or hash)
            rule['rule_id'] = f"rule_{abs(hash(rule['technical_condition']))}" 

        return (jsonify(result_data), 200, headers)

    except Exception as e:
        logging.exception(f"Extract error: {e}")
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
