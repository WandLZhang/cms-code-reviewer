import functions_framework
from flask import jsonify
from google import genai
import os
import json
# import logging
import requests

# logging.basicConfig(level=logging.INFO)

# --- Initialize Google GenAI ---
try:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "wz-cobol-graph")
    client = genai.Client(
        vertexai=True,
        project=project_id,
        location="us-central1",
    )
    print(f"Worker: Gemini initialized for project '{project_id}'", flush=True)
except Exception as e:
    print(f"Worker: Error initializing Gemini: {e}", flush=True)
    client = None

MODEL_NAME = "gemini-3.0-pro-preview"

@functions_framework.http
def link_entities(request):
    """
    Agent 4: Graph Linker / Entity Resolution.
    Maps Rules to Standardized Data Entities (CPT, Rev Code, Variables).
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
        rule = data.get('rule')
        
        if not rule:
            print("Error: Missing rule data", flush=True)
            return (jsonify({'error': 'Missing rule data'}), 400, headers)

        print(f"--- Agent 4 Linking Rule: {rule.get('rule_name')} ---", flush=True)

        if not client:
             if os.environ.get('MOCK_AI'):
                 print("Using Mock AI", flush=True)
                 return (jsonify(mock_linking(rule)), 200, headers)
             print("Error: Gemini client not initialized", flush=True)
        
        prompt = f"""
        You are a Data Lineage Expert.
        Link this Business Rule to the specific Data Entities it governs.
        
        RULE:
        Condition: {rule.get('technical_condition')}
        Explanation: {rule.get('plain_english')}
        Raw Entities: {rule.get('entities_used', [])}
        
        INSTRUCTIONS:
        1. Identify the STANDARD Data Entities involved (e.g., "CPT 99214", "Revenue Code 0421", "Diagnosis Code").
        2. Identify the RELATIONSHIP type (e.g., "Validates", "Calculates", "Routes").
        3. Return ONLY the entities and relationships. Do NOT invent abstract scenarios.
        
        FORMAT:
        {{
            "links": [
                {{
                    "entity_name": "Revenue Code",
                    "entity_value": "0421", 
                    "relationship": "Validates Presence"
                }},
                {{
                    "entity_name": "Payment Amount",
                    "entity_value": "Variable",
                    "relationship": "Calculates"
                }}
            ]
        }}
        """
        
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        
        # Parse JSON
        response_text = response.text.strip()
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()
            
        result_data = json.loads(response_text)
        
        output = {
            "rule_id": rule.get('rule_id'),
            "entity_links": result_data.get('links', [])
        }
        print(f"Linked {len(result_data.get('links', []))} entities", flush=True)

        # Forward to Graph Writer (Persist Rule + Links)
        writer_url = os.environ.get('WRITER_URL')
        if writer_url:
            try:
                print(f"Forwarding to Graph Writer: {writer_url}", flush=True)
                writer_payload = {
                    "program": {}, # Context lost in chain, ignored by writer for partial updates?
                    "sections": [],
                    "rules": [
                        {
                            "rule": rule,
                            "links": result_data.get('links', [])
                        }
                    ]
                }
                requests.post(writer_url, json=writer_payload, timeout=5)
            except Exception as e:
                print(f"Error: Failed to call Writer: {e}", flush=True)

        return (jsonify(output), 200, headers)

    except Exception as e:
        print(f"Linking error: {e}", flush=True)
        return (jsonify({'error': str(e)}), 500, headers)

def mock_linking(rule):
    return {
        "rule_id": rule.get('rule_id'),
        "entity_links": [
            {"entity_name": "Mock Entity", "entity_value": "MOCK", "relationship": "Uses"}
        ]
    }
