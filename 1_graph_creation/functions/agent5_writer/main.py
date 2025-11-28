import functions_framework
from flask import Request, Response, jsonify
import os
import json
from google.cloud import spanner

# Configuration
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "wz-cobol-graph")
INSTANCE_ID = os.environ.get("SPANNER_INSTANCE", "cobol-graph-v2")
DATABASE_ID = os.environ.get("SPANNER_DATABASE", "cobol-graph-db-agent-outputs")

# Initialize Spanner
try:
    spanner_client = spanner.Client(project=PROJECT_ID)
    instance = spanner_client.instance(INSTANCE_ID)
    database = instance.database(DATABASE_ID)
except Exception as e:
    print(f"Error initializing Spanner: {e}")
    database = None

def insert_data(transaction, table_name, records):
    if not records:
        return
    
    # Get columns from first record
    # Ensure we only use columns that exist in schema
    # For safety, we might need to whitelist or filter, but assuming artifacts match schema.
    # We append created_at.
    
    columns = list(records[0].keys())
    if 'created_at' not in columns:
        columns.append('created_at')
        
    values = []
    for record in records:
        row = []
        for col in columns:
            if col == 'created_at':
                row.append(spanner.COMMIT_TIMESTAMP)
            elif col == 'last_analyzed': # For Programs
                row.append(spanner.COMMIT_TIMESTAMP)
            elif col == 'updated_at': # For Programs
                row.append(spanner.COMMIT_TIMESTAMP)
            else:
                row.append(record.get(col))
        values.append(row)

    transaction.insert_or_update(
        table=table_name,
        columns=columns,
        values=values
    )
    print(f"Inserted/Updated {len(values)} rows into {table_name}")

@functions_framework.http
def graph_writer(request: Request):
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
        }
        return ('', 204, headers)

    if not database:
        return jsonify({'error': 'Spanner not initialized'}), 500

    try:
        req_json = request.get_json(silent=True) or {}
        
        # Validate Inputs
        program_id = req_json.get('program_id')
        source_lines = req_json.get('source_lines', [])
        structures = req_json.get('structures', [])
        entities = req_json.get('entities', [])
        flow_data = req_json.get('flow', {})
        
        control_flow = flow_data.get('control_flow', [])
        line_references = flow_data.get('line_references', [])

        if not program_id:
            return jsonify({'error': 'Missing program_id'}), 400

        def write_transaction(transaction):
            # 1. Programs
            # We construct program record. 
            # Assuming source_lines[0] has program info or we just make basic record
            program_record = {
                'program_id': program_id,
                'program_name': program_id, # Default
                'file_name': f"{program_id}.cbl", # Default
                'total_lines': len(source_lines),
                'last_analyzed': spanner.COMMIT_TIMESTAMP,
                'updated_at': spanner.COMMIT_TIMESTAMP
            }
            # If artifacts provided metadata, override
            
            # Insert Programs
            insert_data(transaction, 'Programs', [program_record])

            # 2. CodeStructure
            # Ensure fields match schema: structure_id, program_id, parent_structure_id, name, type, start_line_number, end_line_number
            # Input might have 'start_line' instead of 'start_line_number'
            clean_structures = []
            for s in structures:
                clean_structures.append({
                    'structure_id': s.get('section_id'),
                    'program_id': program_id,
                    'parent_structure_id': s.get('parent_structure_id'),
                    'name': s.get('name'),
                    'type': s.get('type'),
                    'start_line_number': s.get('start_line'),
                    'end_line_number': s.get('end_line')
                })
            insert_data(transaction, 'CodeStructure', clean_structures)

            # 3. SourceCodeLines
            # Schema: line_id, program_id, structure_id, line_number, content, type
            clean_lines = []
            for l in source_lines:
                clean_lines.append({
                    'line_id': l.get('line_id'),
                    'program_id': program_id,
                    'structure_id': l.get('structure_id'),
                    'line_number': l.get('line_number'),
                    'content': l.get('content'),
                    'type': l.get('type') or l.get('line_type', 'CODE')
                })
            insert_data(transaction, 'SourceCodeLines', clean_lines)

            # 4. DataEntities
            # Schema: entity_id, program_id, name, type, definition_line_id, description
            clean_entities = []
            for e in entities:
                clean_entities.append({
                    'entity_id': e.get('entity_id'),
                    'program_id': program_id,
                    'name': e.get('entity_name'),
                    'type': e.get('entity_type'),
                    'definition_line_id': e.get('definition_line_id'),
                    'description': e.get('description')
                })
            insert_data(transaction, 'DataEntities', clean_entities)

            # 5. LineReferences
            # Schema: reference_id, source_line_id, target_entity_id, usage_type
            clean_refs = []
            for r in line_references:
                clean_refs.append({
                    'reference_id': r.get('reference_id'),
                    'source_line_id': r.get('source_line_id'),
                    'target_entity_id': r.get('target_entity_id'),
                    'usage_type': r.get('usage_type')
                })
            insert_data(transaction, 'LineReferences', clean_refs)

            # 6. ControlFlow
            # Schema: flow_id, source_line_id, target_structure_id, type
            clean_flows = []
            for f in control_flow:
                clean_flows.append({
                    'flow_id': f.get('flow_id'),
                    'source_line_id': f.get('source_line_id'),
                    'target_structure_id': f.get('target_structure_id'),
                    'type': f.get('type')
                })
            insert_data(transaction, 'ControlFlow', clean_flows)

        # Execute Transaction
        database.run_in_transaction(write_transaction)
        
        return jsonify({
            'status': 'success',
            'message': f'Successfully wrote graph for {program_id}',
            'stats': {
                'lines': len(source_lines),
                'structures': len(structures),
                'entities': len(entities),
                'flows': len(control_flow),
                'references': len(line_references)
            }
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
