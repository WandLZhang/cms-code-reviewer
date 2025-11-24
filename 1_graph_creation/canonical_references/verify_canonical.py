import argparse
from google.cloud import spanner

def run_query(database, query, query_type="Traceability"):
    print(f"\n--- Running {query_type} Query ---")
    print(query)
    print("-" * 20)
    
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql(query)
        rows = list(results)
        print(f"Found {len(rows)} results:")
        for row in rows:
            print(row)

def main():
    parser = argparse.ArgumentParser(description='Verify Canonical Data in Spanner')
    parser.add_argument('--project_id', required=True, help='GCP Project ID')
    parser.add_argument('--instance_id', required=True, help='Spanner Instance ID')
    parser.add_argument('--database_id', required=True, help='Spanner Database ID')
    args = parser.parse_args()

    spanner_client = spanner.Client(project=args.project_id)
    instance = spanner_client.instance(args.instance_id)
    database = instance.database(args.database_id)

    # 1. Life of a Transaction ("The Policy Map")
    # Maps the Main Control Flow to the Data Checks.
    query_policy_map = """
    GRAPH CobolLineGraph
    MATCH (main:Structure {name: 'MAIN-PARA'})-[:CONTAINS_LINE]->(call_line:Line)-[:CALLS]->(sub:Structure)
    MATCH (sub)-[:CONTAINS_LINE]->(read_line:Line)-[:REFERENCES {usage_type: 'READS'}]->(entity:Entity)
    MATCH (sub)-[:CONTAINS_LINE]->(update_line:Line)-[:REFERENCES {usage_type: 'UPDATES'}]->(status:Entity)
    MATCH (decision_line:Line)-[:REFERENCES {usage_type: 'VALIDATES'}]->(status)
    WHERE decision_line.structure_id = main.structure_id
    RETURN 
      call_line.line_number AS Sequence,
      sub.name AS Routine,
      entity.name AS Entity_Checked,
      decision_line.content AS Logic_Gate
    ORDER BY call_line.line_number
    """
    run_query(database, query_policy_map, "Life of a Transaction (Policy Map)")

if __name__ == '__main__':
    main()
