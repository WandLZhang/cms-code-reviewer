import json
from google.cloud import spanner
import datetime
import os

def load_data():
    instance_id = os.environ.get("SPANNER_INSTANCE", "cobol-graph-instance")
    database_id = os.environ.get("SPANNER_DATABASE", "cobol-graph-db")
    
    print(f"Connecting to Spanner: {instance_id}/{database_id}")
    spanner_client = spanner.Client()
    instance = spanner_client.instance(instance_id)
    database = instance.database(database_id)

    # Load JSON
    json_path = "1_graph_creation/cbtrn01c_data.json"
    print(f"Reading {json_path}...")
    with open(json_path, 'r') as f:
        data = json.load(f)

    with database.batch() as batch:
        print("Starting batch insert...", flush=True)
        
        # 1. Program
        prog = data['program']
        batch.insert_or_update(
            table='Programs',
            columns=['program_id', 'program_name', 'file_name', 'total_lines', 'last_analyzed', 'created_at', 'updated_at'],
            values=[(
                prog['program_id'], prog['program_name'], prog['file_name'], prog['total_lines'],
                spanner.COMMIT_TIMESTAMP, spanner.COMMIT_TIMESTAMP, spanner.COMMIT_TIMESTAMP
            )]
        )
        
        # 2. Sections
        for sec in data['sections']:
            batch.insert_or_update(
                table='CodeSections',
                columns=['section_id', 'program_id', 'section_name', 'section_type', 'start_line', 'end_line', 'content', 'created_at'],
                values=[(
                    sec['section_id'], prog['program_id'], sec['name'], sec['type'], 
                    sec['start_line'], sec['end_line'], sec.get('content', ''), 
                    spanner.COMMIT_TIMESTAMP
                )]
            )

        # 3. Rules & Entities
        for rule in data.get('rules', []):
            batch.insert_or_update(
                table='BusinessRules',
                columns=['rule_id', 'section_id', 'rule_name', 'technical_condition', 'plain_english', 'created_at'],
                values=[(
                    rule['rule_id'], rule['section_id'], rule['rule_name'], 
                    rule['technical_condition'], rule['plain_english'], 
                    spanner.COMMIT_TIMESTAMP
                )]
            )
            
            for link in rule.get('links', []):
                # Scalable Naming: ent_{ProgramID}_{EntityName}
                # This handles the scope correctly for local COBOL definitions.
                ent_id = f"ent_{prog['program_id']}_{link['entity_name']}"
                
                batch.insert_or_update(
                    table='BusinessEntities',
                    columns=['entity_id', 'entity_name', 'entity_type', 'created_at'],
                    values=[(
                        ent_id, link['entity_name'], link['entity_value'], spanner.COMMIT_TIMESTAMP
                    )]
                )
                batch.insert_or_update(
                    table='RuleEntities',
                    columns=['rule_id', 'entity_id', 'usage_type', 'created_at'],
                    values=[(
                        rule['rule_id'], ent_id, link['relationship'], spanner.COMMIT_TIMESTAMP
                    )]
                )

        # 4. Calls
        for call in data.get('section_calls', []):
            batch.insert_or_update(
                table='SectionCalls',
                columns=['call_id', 'source_section_id', 'target_section_id', 'call_type', 'created_at'],
                values=[(
                    call['call_id'], call['source_section_id'], call['target_section_id'], call['type'], spanner.COMMIT_TIMESTAMP
                )]
            )

    print("Data loaded successfully.")

if __name__ == "__main__":
    load_data()
