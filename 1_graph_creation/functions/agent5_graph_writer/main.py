import functions_framework
from flask import jsonify
import logging
import os
from google.cloud import spanner

logging.basicConfig(level=logging.INFO)

@functions_framework.http
def write_graph(request):
    # Lazy Init Spanner to avoid fork issues
    try:
        spanner_client = spanner.Client()
        instance_id = os.environ.get("SPANNER_INSTANCE", "cobol-graph-instance")
        database_id = os.environ.get("SPANNER_DATABASE", "cobol-graph-db")
        instance = spanner_client.instance(instance_id)
        database = instance.database(database_id)
    except Exception as e:
        logging.error(f"Spanner Init Error: {e}")
        database = None
    """
    Agent 5: Graph Writer.
    Commits the processed nodes and edges to Spanner.
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
        program = data.get('program')
        sections = data.get('sections', [])
        rules = data.get('rules', [])
        
        if not database:
             # If local/no-auth, fallback to simulated output
             return (jsonify({"status": "simulated", "message": "No Spanner connection"}), 200, headers)

        # Use Batch for simpler atomic writes
        with database.batch() as batch:
            # 1. Program
            if program:
                props = program.get('properties', {})
                batch.insert_or_update(
                    table='Programs',
                    columns=['program_id', 'program_name', 'file_name', 'total_lines', 'last_analyzed', 'created_at', 'updated_at'],
                    values=[(
                        props.get('program_id'),
                        props.get('program_name'),
                        props.get('file_name'),
                        props.get('total_lines', 0),
                        spanner.COMMIT_TIMESTAMP,
                        spanner.COMMIT_TIMESTAMP,
                        spanner.COMMIT_TIMESTAMP
                    )]
                )

            # 2. Sections
            for section in sections:
                batch.insert_or_update(
                    table='CodeSections',
                    columns=['section_id', 'program_id', 'section_name', 'section_type', 'start_line', 'end_line', 'content', 'created_at'],
                    values=[(
                        section.get('section_id'),
                        program.get('properties', {}).get('program_id'),
                        section.get('section_name'),
                        section.get('type'),
                        section.get('start_line'),
                        section.get('end_line'),
                        "", # Content omitted
                        spanner.COMMIT_TIMESTAMP
                    )]
                )

            # 3. Rules & Links
            for rule_obj in rules:
                rule = rule_obj.get('rule')
                links = rule_obj.get('links', [])
                
                batch.insert_or_update(
                    table='BusinessRules',
                    columns=['rule_id', 'section_id', 'rule_name', 'technical_condition', 'plain_english', 'created_at'],
                    values=[(
                        rule.get('rule_id'),
                        rule.get('section_id'),
                        rule.get('rule_name'),
                        rule.get('technical_condition'),
                        rule.get('plain_english'),
                        spanner.COMMIT_TIMESTAMP
                    )]
                )
                
                for link in links:
                    entity_id = f"ent_{link.get('entity_value')}"
                    
                    # Entity Node
                    batch.insert_or_update(
                        table='BusinessEntities',
                        columns=['entity_id', 'entity_name', 'entity_type', 'description', 'created_at'],
                        values=[(
                            entity_id,
                            link.get('entity_name'),
                            'DataElement',
                            'Extracted from code',
                            spanner.COMMIT_TIMESTAMP
                        )]
                    )
                    
                    # Edge (RuleEntities)
                    batch.insert_or_update(
                        table='RuleEntities',
                        columns=['rule_id', 'entity_id', 'usage_type', 'created_at'],
                        values=[(
                            rule.get('rule_id'),
                            entity_id,
                            link.get('relationship'),
                            spanner.COMMIT_TIMESTAMP
                        )]
                    )
        
        # Batch is committed on exit of context manager

        return (jsonify({
            "status": "success",
            "message": f"Committed graph updates for {program.get('properties', {}).get('program_name')}"
        }), 200, headers)

    except Exception as e:
        logging.exception(f"Write error: {e}")
        return (jsonify({'error': str(e)}), 500, headers)
