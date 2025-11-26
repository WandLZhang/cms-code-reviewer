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

## 2. Agent Deployment Strategy (Refined Pipeline)

We are building a 5-stage agentic pipeline to process COBOL code into a Spanner Graph.

1.  **Agent 1 (Ingest & Lines)**: Ingests source code, creates `Programs` metadata, and classifies individual `SourceCodeLines` (CODE, COMMENT, etc.).
2.  **Agent 2 (Structure)**: Identifies the hierarchy (Divisions, Sections, Paragraphs) and links lines to their parent structure.
3.  **Agent 3 (Entities)**: Parses the Data Division to extract `DataEntities` (Variables, Files).
4.  **Agent 4 (Flow)**: Analyzes the Procedure Division to extract `LineReferences` and `ControlFlow`.
5.  **Agent 5 (Writer)**: Aggregates all objects and commits them to Spanner.

### 2.1. Agent 1: Ingest & Lines (Implemented)

*   **Functionality**: Reads COBOL source (Text or GCS), extracts Program ID using Gemini, classifies lines using Gemini (parallelized).
*   **Source**: `1_graph_creation/functions/agent1_ingest_lines/main.py`
*   **Input**: JSON `{"content": "..."}` or `{"gcs_uri": "..."}`
*   **Output**: NDJSON stream of `metadata` and `line_record` objects.

**Run Locally:**
```bash
source venv/bin/activate
functions-framework \
    --target=ingest_lines \
    --source=1_graph_creation/functions/agent1_ingest_lines/main.py \
    --port=8081 \
    --debug
```

**Test Locally:**
```bash
curl -X POST http://localhost:8081 \
-H "Content-Type: application/json" \
-d '{"content": "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. TEST."}'
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

### 2.2. Agent 2: Structure (Next Step)
*   **Goal**: Consume Agent 1's output. Use Gemini to identify start/end lines of Divisions, Sections, and Paragraphs.
*   **Enrichment**: Update line records with `structure_id`.

### 2.3. Agent 3: Data Entities (Planned)
*   **Goal**: Extract variables and files from Data Division sections identified by Agent 2.

### 2.4. Agent 4: References & Flow (Planned)
*   **Goal**: Analyze Procedure Division lines for entity usage and control flow.

### 2.5. Agent 5: Writer (Planned)
*   **Goal**: Batch write to Spanner `Programs`, `SourceCodeLines`, `CodeStructure`, `DataEntities`, `LineReferences`, `ControlFlow`.

## 3. Current Status

*   [x] **Spanner Schema**: Defined (`1_graph_creation/canonical_references/spanner-schema.sql`)
*   [x] **Agent 1**: Implemented and tested locally.
*   [ ] **Agent 2**: Pending implementation.
*   [ ] **Agent 3**: Pending implementation.
*   [ ] **Agent 4**: Pending implementation.
*   [ ] **Agent 5**: Pending implementation.

## 4. Next Steps

1.  Implement **Agent 2 (Structure)** to process the line stream and build the hierarchy.
2.  Verify Agent 2 output against `02_structure.json`.
