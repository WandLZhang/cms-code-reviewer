#!/bin/bash
set -e

PROJECT_ID="wz-cobol-graph"
REGION="us-central1"

# CD to the directory of this script so --source=. works
cd "$(dirname "$0")"

echo "--- Deploying Agent 4 Worker ---"
gcloud functions deploy agent4-flow-worker \
    --gen2 \
    --region=$REGION \
    --runtime=python311 \
    --source=. \
    --entry-point=flow_worker \
    --trigger-http \
    --allow-unauthenticated \
    --timeout=3600s \
    --memory=4Gi \
    --cpu=2 \
    --set-env-vars=GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_REGION=global

# Get the Worker URL
WORKER_URL=$(gcloud functions describe agent4-flow-worker --gen2 --region=$REGION --format='value(serviceConfig.uri)')
echo "Worker URL: $WORKER_URL"

echo "--- Deploying Agent 4 Orchestrator ---"
gcloud functions deploy agent4-flow-orchestrator \
    --gen2 \
    --region=$REGION \
    --runtime=python311 \
    --source=. \
    --entry-point=flow_orchestrator \
    --trigger-http \
    --allow-unauthenticated \
    --timeout=3600s \
    --memory=4Gi \
    --cpu=2 \
    --set-env-vars=GOOGLE_CLOUD_PROJECT=$PROJECT_ID,WORKER_URL=$WORKER_URL

# Get Orchestrator URL
ORCHESTRATOR_URL=$(gcloud functions describe agent4-flow-orchestrator --gen2 --region=$REGION --format='value(serviceConfig.uri)')
echo "Orchestrator URL: $ORCHESTRATOR_URL"

echo "--- Deployment Complete ---"
