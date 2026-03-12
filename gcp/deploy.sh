#!/usr/bin/env bash
# ============================================
# GCP Deployment Script
# AI Research Assistant Backend
# ============================================
#
# Usage:
#   ./gcp/deploy.sh <project-id> <region>
#
# Example:
#   ./gcp/deploy.sh my-gcp-project us-central1

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <project-id> [region]}"
REGION="${2:-us-central1}"
SERVICE_NAME="research-backend"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "============================================"
echo " Deploying AI Research Assistant Backend"
echo " Project:  ${PROJECT_ID}"
echo " Region:   ${REGION}"
echo " Service:  ${SERVICE_NAME}"
echo "============================================"

# --- 1. Authenticate & set project ---
echo "→ Setting GCP project..."
gcloud config set project "${PROJECT_ID}"

# --- 2. Enable required APIs ---
echo "→ Enabling required APIs..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    artifactregistry.googleapis.com \
    redis.googleapis.com \
    2>/dev/null || true

# --- 3. Build container image ---
echo "→ Building container image..."
gcloud builds submit \
    --tag "${IMAGE}:latest" \
    --timeout=1800s \
    .

# --- 4. Create secrets (if not existing) ---
echo "→ Checking secrets..."
for secret in database-url secret-key redis-url celery-broker-url sentry-dsn; do
    if ! gcloud secrets describe "${secret}" &>/dev/null; then
        echo "  ⚠  Secret '${secret}' does not exist. Create it with:"
        echo "     echo -n 'VALUE' | gcloud secrets create ${secret} --data-file=-"
    fi
done

# --- 5. Deploy to Cloud Run ---
echo "→ Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
    --image "${IMAGE}:latest" \
    --platform managed \
    --region "${REGION}" \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --max-instances 10 \
    --min-instances 0 \
    --timeout 300 \
    --concurrency 80 \
    --set-env-vars "APP_ENV=production,PORT=8000" \
    --set-secrets "\
DATABASE_URL=database-url:latest,\
SECRET_KEY=secret-key:latest,\
REDIS_URL=redis-url:latest,\
CELERY_BROKER_URL=celery-broker-url:latest"

# --- 6. Get service URL ---
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --platform managed \
    --region "${REGION}" \
    --format 'value(status.url)')

echo ""
echo "============================================"
echo " ✅ Deployment Complete!"
echo " URL: ${SERVICE_URL}"
echo " Health: ${SERVICE_URL}/api/v1/health"
echo "============================================"
