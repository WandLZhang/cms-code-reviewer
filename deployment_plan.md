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
    gcloud spanner instances create cobol-graph-instance \
        --config=regional-us-central1 \
        --description="COBOL Graph" \
        --nodes=1 \
        --edition=ENTERPRISE
    ```
    *(Note: If you have a Standard instance, update it: `gcloud spanner instances update cobol-graph-instance --edition=ENTERPRISE`)*

3.  **Create Database:**
    ```bash
    gcloud spanner databases create cobol-graph-db --instance=cobol-graph-instance
    ```

4.  **Apply Schema (including Graph Definition):**
    ```bash
    gcloud spanner databases ddl update cobol-graph-db \
        --instance=cobol-graph-instance \
        --ddl-file=1_graph_creation/spanner-schema.sql
    ```

### 1.2. Cloud Storage (Source Code)
We use GCS to store the raw COBOL files.

1.  **Create Bucket:**
    ```bash
    gcloud storage buckets create gs://wz-cobol-graph-source --location=us-central1
    ```

2.  **Upload Source Code:**
    ```bash
    gcloud storage cp 1_graph_creation/cbl/CBACT01C.cbl gs://wz-cobol-graph-source/CBACT01C.cbl
    ```

## 2. Agent Deployment Strategy (Hybrid)

We use a hybrid approach where ingestion and orchestration happen locally (or in a lightweight environment), while heavy AI processing (Rule Extraction) runs as a scalable Cloud Function.

### 2.1. Agent 1 & 2 (Local / Orchestrator)
*   **Agent 1 (Ingest):** Runs locally. Downloads source, hands off to Agent 2 asynchronously.
*   **Agent 2 (Parse):** Runs locally. Parses structure, handles **parallel fan-out** to Agent 3 with retry logic.

**Run Locally:**
```bash
# Terminal 1
source venv/bin/activate
AGENT2_URL=http://localhost:8082 functions-framework --target=ingest_source --source=1_graph_creation/functions/agent1_ingest_source/main.py --port=8081 --debug 2>&1 | tee agent1.txt

# Terminal 2
source venv/bin/activate
# Point to Cloud Agent 3
AGENT3_URL=https://us-central1-wz-cobol-graph.cloudfunctions.net/agent3-extract-rules \
WRITER_URL=http://localhost:8085 \
functions-framework --target=parse_structure --source=1_graph_creation/functions/agent2_parse_structure/main.py --port=8082 --debug 2>&1 | tee agent2.txt
```

### 2.2. Agent 3 (Cloud / Worker)
*   **Agent 3 (Extract):** Deployed as a **Cloud Function (Gen 2)**.
*   **Model:** Uses **Gemini 3.0 Pro Preview** (via Vertex AI).
*   **Scaling:** Configured for `max-instances=1000` and `concurrency=3` to handle massive parallel loads from Agent 2.

**Deploy Command:**
```bash
gcloud functions deploy agent3-extract-rules \
    --gen2 \
    --region=us-central1 \
    --runtime=python311 \
    --source=1_graph_creation/functions/agent3_extract_rules \
    --entry-point=extract_rules \
    --trigger-http \
    --allow-unauthenticated \
    --max-instances=1000 \
    --concurrency=3 \
    --timeout=540s \
    --memory=4Gi \
    --cpu=2 \
    --set-env-vars=GOOGLE_CLOUD_PROJECT=wz-cobol-graph,LOG_EXECUTION_ID=true
```

### 2.3. Agent 4 & 5 (Pending Deployment)
*   **Agent 4 (Link):** Will be deployed to Cloud Functions (similar spec to Agent 3) to handle entity linking at scale.
*   **Agent 5 (Writer):** Writes to Spanner. Can be local or cloud.

## 3. Current Status & Caveats

### 3.1. Status (As of Latest Run)
*   **Traceability Query:** **Supported**. The pipeline successfully extracts business rules and links them to entities (once Agent 4 is online).
*   **Execution Flow (Tree Query):** **Partially Supported**. The logic is extracted, but the graph schema lacks explicit `[:CALLS]` edges between sections.

### 3.2. Caveats for Execution Flow
To fully enable the "Execution Tree" query (`(Section)-[:CALLS*]->(Section)`), we are implementing updates with the following constraints:

1.  **Internal Paragraphs (`PERFORM 1000-MAIN`)**:
    *   **Status:** Solvable. We map the target name to the Section ID within the same program.
    *   **Action:** Agent 5 will be updated to create `[:CALLS]` edges for these.

2.  **External Program Calls (`CALL 'SUBPROG'`)**:
    *   **Status:** Requires cross-program linking.
    *   **Action:** Agent 5 must detect `CALL` (vs `PERFORM`) and link to a `Program` node instead of a `Section` node.

3.  **Dynamic Calls (`CALL WS-VAR`)**:
    *   **Status:** **Unsolvable Static Analysis**. Since the target is a variable determined at runtime, we cannot draw a static graph edge to a specific program.
    *   **Mitigation:** We link to the *Variable Entity* (`WS-VAR`), but the graph traversal stops there.

## 4. Next Steps
1.  **Schema Update:** Add `SectionCalls` table/edge to `spanner-schema.sql`.
2.  **Logic Update:** Modify Agent 3 prompt to explicitly extract Flow Control targets.
3.  **Writer Update:** Update Agent 5 to write these edges.
4.  **Deploy:** Agent 4 & 5 to Cloud.
