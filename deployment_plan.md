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

We have built a 5-stage agentic pipeline to process COBOL code into a Spanner Graph.

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

### 2.1. Agent 1: Ingest & Lines (✅ Complete)

*   **Functionality**: Reads COBOL source (Text or GCS), extracts Program ID using Gemini, classifies lines using Gemini (parallelized).
*   **Source**: `1_graph_creation/functions/agent1_ingest_lines/main.py`
*   **Output**: `01_source_lines.json`.

### 2.2. Agent 2: Structure

*   **Functionality**: Consumes Agent 1's output. Uses Gemini to identify structure.
*   **Enrichment**: Includes `enrich_source_lines.py` to bake `structure_id` into `01_source_lines_enriched.json`.
*   **Source**: `1_graph_creation/functions/agent2_structure/main.py`
*   **Output**: `02_structure.json`, `01_source_lines_enriched.json`.

### 2.3. Agent 3: Data Entities

*   **Functionality**: Extracts data entities (Files, Variables) using Gemini LLM extraction per structure. Includes conflict resolution.
*   **Architecture**: Orchestrator-Worker pattern.
*   **Source**: `1_graph_creation/functions/agent3_entities/main.py`
*   **Output**: `03_entities.json`.

### 2.4. Agent 4: References & Flow

*   **Functionality**: Analyzes ALL structures to find Control Flow (`PERFORM`) and Line References (`READS`, `UPDATES`).
*   **Architecture**: Orchestrator-Worker pattern.
    *   **Orchestrator**: Iterates structures, sends full file context + target structure ID to worker.
    *   **Worker**: Uses Gemini 3 to analyze specific structure lines within full file context.
*   **Source**: `1_graph_creation/functions/agent4_flow/main.py`
*   **Output**: `04_references_and_flow.json`.
*   **Verification**: 100% coverage of canonical flows + 2 new flows found.

### 2.5. Agent 5: Graph Writer

*   **Goal**: Batch write all artifacts to Spanner.
*   **Basis**: Based on `load_canonical.py`.
*   **Logic**:
    *   Insert `Programs`.
    *   Insert `CodeStructure`.
    *   Insert `SourceCodeLines`.
    *   Insert `DataEntities`.
    *   Insert `LineReferences` & `ControlFlow`.
*   **Target**: Spanner DB `cobol-graph-db-agent-outputs`.

## 3. Canonical Query Target

The ultimate goal is to enable this GQL query:

```gql
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
