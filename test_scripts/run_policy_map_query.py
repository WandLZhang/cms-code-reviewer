from google.cloud import spanner

def run_query(database, query):
    print(f"\n--- Running Policy Map Query ---")
    print(query)
    print("-" * 20)
    
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql(query)
        rows = list(results)
        print(f"Found {len(rows)} results:")
        for row in rows:
            print(row)

def main():
    PROJECT_ID = "wz-cobol-graph"
    INSTANCE_ID = "cobol-graph-v2"
    DATABASE_ID = "cobol-graph-db-agent-outputs"

    spanner_client = spanner.Client(project=PROJECT_ID)
    instance = spanner_client.instance(INSTANCE_ID)
    database = instance.database(DATABASE_ID)

    # Query from canonical_queries.txt
    query = """
    GRAPH CobolLineGraph
    MATCH (main:Structure {name: 'MAIN-PARA'})-[:CONTAINS_LINE]->(call_line:Line)-[:CALLS]->(sub:Structure)
    MATCH (main)-[:CONTAINS_LINE]->(decision_line:Line)-[:REFERENCES {usage_type: 'VALIDATES'}]->(status:Entity)
    MATCH (sub)-[:CONTAINS_LINE]->(action_line:Line)-[ref:REFERENCES]->(entity:Entity)
    RETURN 
      call_line.line_number AS Sequence,
      sub.name AS Routine,
      decision_line.content AS Logic_Gate,
      action_line.content AS Source_Code,
      ref.usage_type AS Operation,
      entity.name AS Data_Object,
      entity.type AS Entity_Type,
      entity.description AS Description
    ORDER BY Sequence, action_line.line_number
    """
    
    run_query(database, query)

if __name__ == '__main__':
    main()
