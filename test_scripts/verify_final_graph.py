import argparse
from google.cloud import spanner

def run_query(database, query):
    print(f"\n--- Running Graph Query ---")
    print(query)
    print("-" * 20)
    
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql(query)
        rows = list(results)
        print(f"Found {len(rows)} results.")
        for i, row in enumerate(rows):
            print(f"\n[Result {i+1}]")
            # Row items are accessible by index or name if mapped
            # GQL returns struct/json usually.
            print(row)

def main():
    PROJECT_ID = "wz-cobol-graph"
    INSTANCE_ID = "cobol-graph-v2"
    DATABASE_ID = "cobol-graph-db-agent-outputs"

    spanner_client = spanner.Client(project=PROJECT_ID)
    instance = spanner_client.instance(INSTANCE_ID)
    database = instance.database(DATABASE_ID)

    query = """
    GRAPH CobolLineGraph
    MATCH p1 = (main:Structure {name: 'MAIN-PARA'})-[:CONTAINS_LINE]->(call_line:Line)-[:CALLS]->(sub:Structure)
    MATCH p2 = (sub)-[:CONTAINS_LINE]->(read_line:Line)-[:REFERENCES {usage_type: 'READS'}]->(entity:Entity)
    MATCH p3 = (sub)-[:CONTAINS_LINE]->(update_line:Line)-[:REFERENCES {usage_type: 'UPDATES'}]->(status:Entity)
    MATCH p4 = (main)-[:CONTAINS_LINE]->(decision_line:Line)-[:REFERENCES {usage_type: 'VALIDATES'}]->(status)
    RETURN 
      TO_JSON(p1) AS call_flow,
      TO_JSON(p2) AS data_read,
      TO_JSON(p3) AS status_update,
      TO_JSON(p4) AS validation_gate
    ORDER BY call_line.line_number ASC
    LIMIT 5
    """
    
    run_query(database, query)

if __name__ == '__main__':
    main()
