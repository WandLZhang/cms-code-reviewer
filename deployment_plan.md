# COBOL Knowledge Graph Deployment & Setup Guide

This guide details the steps to set up the infrastructure and run the agent pipeline.

## 1. Infrastructure Setup

### 1.1. Spanner (Knowledge Graph Database)
We use Cloud Spanner Enterprise edition to support Spanner Graph.

1.  **Set Project:**
    ```bash
    gcloud config set project wz-cobol-graph
    ```

2.  **Create Instance (Enterprise):**
    ```bash
    gcloud spanner instances create cobol-graph-v2 \
        --config=regional-us-central1 \
        --description="COBOL Graph" \
        --nodes=1 \
        --edition=ENTERPRISE
    ```
    *(Note: If you have a Standard instance, update it: `gcloud spanner instances update cobol-graph-v2 --edition=ENTERPRISE`)*

3.  **Create Database:**
    ```bash
    gcloud spanner databases create cobol-graph-db --instance=cobol-graph-v2
    ```

4.  **Apply Schema (including Graph Definition):**
    ```bash
    gcloud spanner databases ddl update cobol-graph-db \
        --instance=cobol-graph-v2 \
        --ddl-file=1_graph_creation/canonical_references/spanner-schema.sql
    ```

### 1.2. Cloud Storage (Source Code)
We use GCS to store the raw COBOL files.

1.  **Create Bucket:**
    ```bash
    gcloud storage buckets create gs://wz-cobol-graph-source --location=us-central1
    ```

2.  **Upload Source Code:**
    ```bash
    gcloud storage cp 1_graph_creation/source_cbl/CBTRN01C.cbl gs://wz-cobol-graph-source/CBTRN01C.cbl
    ```

## 2. Agent Pipeline Architecture

We are building a 5-stage agentic pipeline to process COBOL code into a Spanner Graph.

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Agent 1       │     │   Agent 2       │     │   Agent 3       │     │   Agent 4       │     │   Agent 5       │
│   Ingest &      │────▶│   Structure     │────▶│   Entities      │────▶│   References &  │────▶│   Graph Writer  │
│   Lines         │     │   Parser        │     │   Extractor     │     │   Flow          │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
       │                       │                       │                       │                       │
       ▼                       ▼                       ▼                       ▼                       ▼
  01_source_lines.json   02_structure.json      03_entities.json    04_references_and_flow.json    Spanner Graph
```

### 2.1. Agent 1: Ingest & Lines 

*   **Functionality**: Reads COBOL source (Text or GCS), extracts Program ID using Gemini, classifies lines using Gemini (parallelized).
*   **Source**: `1_graph_creation/functions/agent1_ingest_lines/main.py`
*   **Input**: JSON `{"content": "..."}` or `{"gcs_uri": "..."}`
*   **Output**: `01_source_lines.json` - NDJSON stream of `metadata` and `line_record` objects.

**Run Locally:**
```bash
cd 1_graph_creation/functions/agent1_ingest_lines
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
```

**Deploy to Cloud Functions:**
```bash
gcloud functions deploy agent1-ingest-lines \
    --gen2 \
    --region=us-central1 \
    --runtime=python311 \
    --source=1_graph_creation/functions/agent1_ingest_lines \
    --entry-point=ingest_lines \
    --trigger-http \
    --allow-unauthenticated \
    --timeout=300s \
    --memory=2Gi \
    --cpu=1 \
    --set-env-vars=GOOGLE_CLOUD_PROJECT=wz-cobol-graph
```

### 2.2. Agent 2: Structure 

*   **Functionality**: Consumes Agent 1's output. Uses Gemini to identify start/end lines of Divisions, Sections, and Paragraphs. Builds hierarchical structure with parent-child relationships.
*   **Source**: `1_graph_creation/functions/agent2_structure/main.py`
*   **Input**: `01_source_lines.json`
*   **Output**: `02_structure.json` - Array of structure objects with `section_id`, `name`, `type`, `start_line`, `end_line`, `parent_structure_id`, `content`.

**Run Locally:**
```bash
cd 1_graph_creation/functions/agent2_structure
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### 2.3. Agent 3: Data Entities 

*   **Functionality**: Iterates through structures from Agent 2, extracts data entities (Files, Variables) using Gemini LLM extraction per structure. Performs Python-based duplicate detection with LLM conflict resolution for merging overlapping entity definitions.
*   **Source**: `1_graph_creation/functions/agent3_entities/main.py`
*   **Input**: `01_source_lines.json` (for line IDs) + `02_structure.json` (for structures)
*   **Output**: `03_entities.json` - Master list of entities with:
    - `entity_name`: Variable or File name
    - `entity_type`: "FILE" or "VARIABLE"
    - `definition_line_id`: Line ID where entity is defined
    - `description`: LLM-generated description
    - `program_id`: Source program

**Run Locally:**
```bash
cd 1_graph_creation/functions/agent3_entities
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
```

**Current Status**: Running locally, processing 28 structures, extracting ~50 entities to match canonical.

**Future Optimization - Parallel Subagents:**
The current sequential approach with conflict resolution is slow due to:
1. Overlapping structures (DIVISION → SECTION → PARAGRAPH nesting) causing redundant processing
2. LLM calls for every conflict (~7-10 sec each)

**Proposed Architecture:**
```
                     ┌──────────────────────────┐
                     │    Agent 3 Orchestrator   │
                     └──────────────────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
    ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
    │  Subagent 3a  │    │  Subagent 3b  │    │  Subagent 3c  │
    │  ENVIRONMENT  │    │  DATA DIV     │    │  PROCEDURE    │
    │  DIVISION     │    │  (FILE/WS)    │    │  DIVISION     │
    └───────────────┘    └───────────────┘    └───────────────┘
            │                    │                    │
            └────────────────────┼────────────────────┘
                                 ▼
                     ┌──────────────────────────┐
                     │   Aggregator & Merger    │
                     │   (LLM call for   │
                     │    each conflict)        │
                     └──────────────────────────┘
```

This would enable:
- Parallel Cloud Functions for each major structure
- Single aggregation/merge step at the end
- Reduced total execution time from ~25 min to ~5 min

### TODO: 2.4. Agent 4: References & Flow

**Goal**: Analyze Procedure Division lines to extract:
1. **Control Flow** (`control_flow`): PERFORM statements that call other paragraphs
2. **Line References** (`line_references`): Entity usage with type (READS, UPDATES, VALIDATES)

**Input Required:**
- `02_structure.json` - To know which lines belong to which paragraph
- `03_entities.json` - Master list of entities to reference

**Output**: `04_references_and_flow.json` with two arrays:

```json
{
  "control_flow": [
    {
      "flow_id": "flow_CBTRN01C_157",
      "source_line_id": "CBTRN01C_157",
      "target_structure_id": "sec_CBTRN01C_0000-DALYTRAN-OPEN",
      "type": "PERFORM"
    }
  ],
  "line_references": [
    {
      "reference_id": "ref_CBTRN01C_170_WS-XREF-READ-STATUS",
      "source_line_id": "CBTRN01C_170",
      "target_entity_name": "WS-XREF-READ-STATUS",
      "usage_type": "UPDATES"
    }
  ]
}
```

**Implementation Strategy:**

1. **Control Flow Extraction:**
   - Scan PROCEDURE DIVISION lines for `PERFORM` statements
   - Match target paragraph name to `structure_id` from `02_structure.json`
   - Generate `flow_id` as `flow_{program_id}_{line_number}`

2. **Line References Extraction:**
   - For each line in PROCEDURE DIVISION:
     - Use LLM to identify which entities from `03_entities.json` are referenced
     - Classify usage type:
       - `READS`: Entity value is read (source of MOVE, displayed, used in condition)
       - `UPDATES`: Entity value is modified (target of MOVE, computed)
       - `VALIDATES`: Entity is used in IF/EVALUATE condition

3. **LLM Prompt Design:**
```
Given this COBOL line:
   MOVE DALYTRAN-STATUS TO IO-STATUS

And these known entities: [DALYTRAN-STATUS, IO-STATUS, APPL-RESULT, ...]

Extract references:
- DALYTRAN-STATUS: READS (source of MOVE)
- IO-STATUS: UPDATES (target of MOVE)
```

**Why This Enables the Canonical Query:**

The canonical query ("Life of a Transaction") requires:
```gql
MATCH (main:Structure)-[:CONTAINS_LINE]->(call_line:Line)-[:CALLS]->(sub:Structure)
MATCH (sub)-[:CONTAINS_LINE]->(read_line:Line)-[:REFERENCES {usage_type: 'READS'}]->(entity:Entity)
```

Agent 4's output creates the edges:
- `control_flow` → `CALLS` edges (Line to Structure)
- `line_references` → `REFERENCES` edges with `usage_type` property (Line to Entity)

### 2.5. Agent 5: Graph Writer 📋 PLANNED

*   **Goal**: Batch write all artifacts to Spanner:
    - `Programs` table from metadata
    - `SourceCodeLines` table from `01_source_lines.json`
    - `CodeStructure` table from `02_structure.json`
    - `DataEntities` table from `03_entities.json`
    - `ControlFlow` table from `04_references_and_flow.json`
    - `LineReferences` table from `04_references_and_flow.json`

## 3. Current Status

| Agent | Status | Artifact | Notes |
|-------|--------|----------|-------|
| Agent 1 | ✅ Complete | `01_source_lines.json` | Local execution verified |
| Agent 2 | ✅ Complete | `02_structure.json` | 28 structures extracted |
| Agent 3 | 🔄 Running | `03_entities.json` | Processing 50 entities, ~20 min remaining |
| Agent 4 | 📋 Planned | `04_references_and_flow.json` | Design complete, implementation next |
| Agent 5 | 📋 Planned | Spanner Graph | After Agent 4 complete |

## 4. Canonical Query Target

The ultimate goal is to enable this GQL query:

```gql
-- "Life of a Transaction" - Show validation gates a transaction passes through

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
```

This query traces transaction processing through:
1. MAIN-PARA calls to subroutines (2000-LOOKUP-XREF, 3000-READ-ACCOUNT)
2. What entities those subroutines READ
3. What status variables they UPDATE
4. How MAIN-PARA VALIDATES those status variables

## 5. Next Steps

1. ✅ Wait for Agent 3 to complete (~12:25-12:30 PM)
2. 📋 Verify Agent 3 output matches canonical `03_entities.json` (50 entities)
3. 📋 Implement Agent 4: References & Flow
4. 📋 Verify Agent 4 output matches canonical `04_references_and_flow.json`
5. 📋 Implement Agent 5: Graph Writer
6. 📋 Load data to Spanner and run canonical query
