import argparse
from google.cloud import spanner

def run_query(database, query):
    print(f"\n--- Running Grand Unified Query ---")
    print(query)
    print("-" * 20)
    
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql(query)
        rows = list(results)
        print(f"Found {len(rows)} results.")
        
        # Group by Sequence (Call)
        current_seq = None
        
        for row in rows:
            # Unpack row: Sequence, Routine, Source_Code, Operation, Data_Object, Object_Type, Description
            seq = row[0]
            routine = row[1]
            code = row[2].strip()
            op = row[3]
            obj = row[4]
            obj_type = row[5]
            desc = row[6] if len(row) > 6 else "N/A"
            
            if seq != current_seq:
                print(f"\n[Seq {seq}] Calling {routine}")
                current_seq = seq
            
            print(f"  {code}")
            print(f"    -> {op} {obj} ({obj_type})")
            # print(f"       Desc: {desc[:50]}...")

def main():
    PROJECT_ID = "wz-cobol-graph"
    INSTANCE_ID = "cobol-graph-v2"
    DATABASE_ID = "cobol-graph-db-agent-outputs"

    spanner_client = spanner.Client(project=PROJECT_ID)
    instance = spanner_client.instance(INSTANCE_ID)
    database = instance.database(DATABASE_ID)

    query = """
    GRAPH CobolLineGraph
    MATCH (main:Structure {name: 'MAIN-PARA'})-[:CONTAINS_LINE]->(call_line:Line)-[:CALLS]->(sub:Structure)
    MATCH (sub)-[:CONTAINS_LINE]->(action_line:Line)-[ref:REFERENCES]->(entity:Entity)
    RETURN
      call_line.line_number AS Sequence,
      sub.name AS Routine,
      action_line.content AS Source_Code,
      ref.usage_type AS Operation,
      entity.name AS Data_Object,
      entity.type AS Object_Type,
      entity.description AS Description
    ORDER BY Sequence, action_line.line_number
    """
    
    run_query(database, query)

if __name__ == '__main__':
    main()
