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

    # 1. Traceability: Show lines referencing 'XREF-FILE'
    # Adapted for Line-Centric Schema: Entity <-[:REFERENCES]- Line
    query_traceability = """
    GRAPH CobolLineGraph
    MATCH (e:Entity {name: 'XREF-FILE'})<-[:REFERENCES]-(l:Line)
    RETURN l.line_number, l.content, e.name
    """
    run_query(database, query_traceability, "Traceability (XREF-FILE)")

    # 2. Execution Flow (One Hop): Show calls from lines
    # Adapted: Line -[:CALLS]-> Structure
    query_flow = """
    GRAPH CobolLineGraph
    MATCH (l:Line)-[:CALLS]->(s:Structure)
    RETURN l.line_number, l.content, s.name
    """
    run_query(database, query_flow, "Execution Flow (Line -> Structure)")

if __name__ == '__main__':
    main()
