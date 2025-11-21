# COBOL Knowledge Graph Deployment & Setup Guide

This guide details the steps to set up the infrastructure and run the agent pipeline locally (simulating a cloud environment).

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

## 2. Local Agent Setup

### 2.1. Dependencies
Ensure you have a virtual environment with all requirements installed.

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
find 1_graph_creation/functions -name "requirements.txt" -exec pip install -r {} \;
```

### 2.2. Start Agents (Local Simulation)
We run each agent as a separate local server using `functions-framework`. They are chained via environment variables.

*   **Agent 1 (Ingest):** Port 8081 -> Calls Agent 2
*   **Agent 2 (Parse):** Port 8082 -> Calls Agent 3 (Fan-out) & Writer
*   **Agent 3 (Extract):** Port 8083 -> Calls Agent 4
*   **Agent 4 (Link):** Port 8084 -> Calls Writer
*   **Agent 5 (Graph Writer):** Port 8085 -> Writes to Spanner

**Run the startup script:**
```bash
chmod +x test_scripts/start_servers.sh
./test_scripts/start_servers.sh
```

## 3. Execution & Verification

### 3.1. Trigger the Pipeline
Send a request to Agent 1 with the GCS URI of the source file.

```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"gcs_uri": "gs://wz-cobol-graph-source/CBACT01C.cbl"}' \
     http://localhost:8081
```

### 3.2. Monitor Logs
The `start_servers.sh` script redirects logs to `agent*.log` files. You can tail them to see the flow.

```bash
tail -f agent*.log
```

### 3.3. Verify Data in Spanner
Run a SQL query to confirm data insertion.

```bash
gcloud spanner databases execute-sql cobol-graph-db \
    --instance=cobol-graph-instance \
    --sql="SELECT count(*) FROM BusinessRules"
```

Or a Graph Query (GQL) if supported by the CLI/Console.
