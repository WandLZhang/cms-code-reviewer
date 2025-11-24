import argparse
import json
import os
from google.cloud import spanner

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def insert_data(database, table_name, records):
    if not records:
        print(f"No records to insert for {table_name}")
        return

    def insert_transaction(transaction):
        # Prepare columns and values
        columns = list(records[0].keys())
        # Add created_at timestamp
        columns.append('created_at')
        
        values = []
        for record in records:
            row = [record.get(col) for col in columns[:-1]]
            row.append(spanner.COMMIT_TIMESTAMP)
            values.append(row)

        transaction.insert_or_update(
            table=table_name,
            columns=columns,
            values=values
        )
        print(f"Inserted/Updated {len(values)} rows into {table_name}")

    database.run_in_transaction(insert_transaction)

def main():
    parser = argparse.ArgumentParser(description='Load Canonical JSONs into Spanner')
    parser.add_argument('--project_id', required=True, help='GCP Project ID')
    parser.add_argument('--instance_id', required=True, help='Spanner Instance ID')
    parser.add_argument('--database_id', required=True, help='Spanner Database ID')
    args = parser.parse_args()

    # Initialize Spanner Client
    spanner_client = spanner.Client(project=args.project_id)
    instance = spanner_client.instance(args.instance_id)
    database = instance.database(args.database_id)

    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Load Programs (from 01_source_lines.json metadata)
    print("Loading Programs...")
    source_lines_data = load_json(os.path.join(base_dir, '01_source_lines.json'))
    program_meta = source_lines_data['program']
    
    # Programs Table
    program_record = {
        'program_id': program_meta['program_id'],
        'program_name': program_meta['program_name'],
        'file_name': program_meta['file_name'],
        'total_lines': program_meta['total_lines'],
        'last_analyzed': spanner.COMMIT_TIMESTAMP, # Placeholder, will be overridden by allow_commit_timestamp logic or handled separately
        'updated_at': spanner.COMMIT_TIMESTAMP
    }
    # Handling timestamps differently for Programs as it has specific timestamp fields
    def insert_program(transaction):
        columns = ['program_id', 'program_name', 'file_name', 'total_lines', 'last_analyzed', 'created_at', 'updated_at']
        values = [[
            program_record['program_id'],
            program_record['program_name'],
            program_record['file_name'],
            program_record['total_lines'],
            spanner.COMMIT_TIMESTAMP,
            spanner.COMMIT_TIMESTAMP,
            spanner.COMMIT_TIMESTAMP
        ]]
        transaction.insert_or_update(table='Programs', columns=columns, values=values)
        print("Inserted/Updated Program record")
    
    database.run_in_transaction(insert_program)


    # 3. Load CodeStructure (Must load first to calculate structure_id for lines)
    print("Loading CodeStructure...")
    structure_data = load_json(os.path.join(base_dir, '02_structure.json'))
    structure_records = []
    line_to_structure_map = {} # Map line_number -> structure_id (Paragraph priority)

    # Sort structures to process Divisions, then Sections, then Paragraphs
    # This ensures Paragraphs overwrite broader scopes in the map
    sorted_structures = sorted(structure_data['structure'], key=lambda x: {'DIVISION': 1, 'SECTION': 2, 'PARAGRAPH': 3}.get(x['type'], 0))

    for item in sorted_structures:
        record = {
            'structure_id': item['section_id'],
            'program_id': program_meta['program_id'], 
            'parent_structure_id': item['parent_structure_id'],
            'name': item['name'],
            'type': item['type'],
            'start_line_number': item['start_line'],
            'end_line_number': item['end_line']
        }
        structure_records.append(record)
        
        # Map lines to this structure
        for line_num in range(item['start_line'], item['end_line'] + 1):
            line_to_structure_map[line_num] = item['section_id']

    insert_data(database, 'CodeStructure', structure_records)

    # 2. Load SourceCodeLines
    print("Loading SourceCodeLines...")
    source_lines = source_lines_data['source_code_lines']
    # Add structure_id to each line record
    for line in source_lines:
        line['structure_id'] = line_to_structure_map.get(line['line_number'])
        
    insert_data(database, 'SourceCodeLines', source_lines)

    # 4. Load DataEntities
    print("Loading DataEntities...")
    entities_data = load_json(os.path.join(base_dir, '03_entities.json'))
    # JSON: entity_name, entity_type, program_id
    # Schema: entity_id, program_id, name, type, definition_line_id, description
    
    entity_records = []
    for item in entities_data['entities']:
        # Generate a deterministic entity_id or use a convention? 
        # Schema says entity_id STRING. Let's create one: {program_id}_{entity_name}
        entity_id = f"{item['program_id']}_{item['entity_name']}"
        record = {
            'entity_id': entity_id,
            'program_id': item['program_id'],
            'name': item['entity_name'],
            'type': item['entity_type'],
            'definition_line_id': None, # Not in JSON currently
            'description': None
        }
        entity_records.append(record)
    insert_data(database, 'DataEntities', entity_records)

    # 5. Load LineReferences & ControlFlow
    print("Loading References and Flow...")
    ref_flow_data = load_json(os.path.join(base_dir, '04_references_and_flow.json'))

    # LineReferences
    # JSON: reference_id, source_line_id, target_entity_name, usage_type
    # Schema: reference_id, source_line_id, target_entity_id, usage_type
    line_ref_records = []
    for item in ref_flow_data['line_references']:
        # resolve target_entity_id from name
        target_entity_id = f"{program_meta['program_id']}_{item['target_entity_name']}"
        record = {
            'reference_id': item['reference_id'],
            'source_line_id': item['source_line_id'],
            'target_entity_id': target_entity_id,
            'usage_type': item['usage_type']
        }
        line_ref_records.append(record)
    insert_data(database, 'LineReferences', line_ref_records)

    # ControlFlow
    # JSON: flow_id, source_line_id, target_structure_id, type
    # Schema: flow_id, source_line_id, target_structure_id, type
    control_flow_records = []
    for item in ref_flow_data['control_flow']:
        record = {
            'flow_id': item['flow_id'],
            'source_line_id': item['source_line_id'],
            'target_structure_id': item['target_structure_id'],
            'type': item['type']
        }
        control_flow_records.append(record)
    insert_data(database, 'ControlFlow', control_flow_records)

    print("Canonical Data Load Complete!")

if __name__ == '__main__':
    main()
