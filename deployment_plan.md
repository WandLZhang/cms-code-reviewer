This plan tracks the steps to create a Spanner Knowledge Graph from COBOL source code then in the future enabling payment decision tree analysis.

## 2. Schema Definition
- [x] Update `spanner-schema.txt` to include `CREATE PROPERTY GRAPH` statements
- [x] Define Nodes: Program, BusinessRule, Entity, PaymentScenario
- [x] Define Edges: CONTAINS, USES, MAPS_TO, CALLS, EXPLAINED_BY
- [x] Validate schema against Spanner Graph DDL syntax

## 3. Data Ingestion Architecture (Cloud Functions)
We implemented an event-driven architecture using 5 Cloud Functions:
- [x] **`agent1-ingest-source`**: Ingests COBOL, creates Program node.
- [x] **`agent2-parse-structure`**: Parses structure, validates coverage, creates CodeSection nodes.
- [x] **`agent3-extract-rules`**: Uses Vertex AI to extract BusinessRules from code.
- [x] **`agent4-map-scenarios`**: Uses Vertex AI to link Rules to standardized Entities (CPT/Rev Codes).
- [x] **`graph-writer`**: Commits graph nodes/edges to Spanner using `INSERT OR UPDATE`.

## 4. Verification
- [ ] Deploy/Apply schema to Spanner (Emulator or Cloud)
- [ ] Run ingestion for `HHCAL088`
- [ ] Execute GQL query to trace payment logic
