#!/bin/bash
set -e

PROJECT=${GCP_PROJECT:-"venueflow-hackathon-2026"}
REGION="asia-south1"
SERVICE="venueflow"
IMAGE="gcr.io/$PROJECT/$SERVICE"

echo "==> Project: $PROJECT"
echo "==> Region:  $REGION"
echo ""

echo "==> Step 1: Building and pushing Docker image..."
gcloud builds submit \
  --tag "$IMAGE" \
  --project "$PROJECT" \
  --timeout=600s

echo ""
echo "==> Step 2: Deploying to Cloud Run..."
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --min-instances 0 \
  --max-instances 10 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --concurrency 80 \
  --set-env-vars "GCP_PROJECT=$PROJECT,REGION=$REGION" \
  --project "$PROJECT"

echo ""
echo "==> Done! Your live URL:"
gcloud run services describe "$SERVICE" \
  --region "$REGION" \
  --format="value(status.url)" \
  --project "$PROJECT"
