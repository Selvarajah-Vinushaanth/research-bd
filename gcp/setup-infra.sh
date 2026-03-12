#!/usr/bin/env bash
# ============================================
# GCP Infrastructure Setup Script
# One-time setup for Cloud SQL, Redis, Secrets
# ============================================
#
# Usage:
#   ./gcp/setup-infra.sh <project-id> <region>

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <project-id> [region]}"
REGION="${2:-us-central1}"

echo "============================================"
echo " Setting up GCP Infrastructure"
echo " Project: ${PROJECT_ID}"
echo " Region:  ${REGION}"
echo "============================================"

gcloud config set project "${PROJECT_ID}"

# --- Cloud SQL (PostgreSQL 16) ---
echo ""
echo "→ Creating Cloud SQL instance..."
INSTANCE_NAME="research-db"
DB_NAME="research_assistant"

gcloud sql instances create "${INSTANCE_NAME}" \
    --database-version=POSTGRES_16 \
    --tier=db-custom-2-4096 \
    --region="${REGION}" \
    --storage-auto-increase \
    --storage-size=20GB \
    --backup \
    --maintenance-window-day=SUN \
    --maintenance-window-hour=2 \
    --availability-type=zonal \
    2>/dev/null || echo "  Instance may already exist."

# Set root password
DB_PASSWORD=$(openssl rand -base64 24)
gcloud sql users set-password postgres \
    --instance="${INSTANCE_NAME}" \
    --password="${DB_PASSWORD}"

# Create database
gcloud sql databases create "${DB_NAME}" \
    --instance="${INSTANCE_NAME}" \
    2>/dev/null || echo "  Database may already exist."

echo "  ✅ Cloud SQL instance: ${INSTANCE_NAME}"
echo "  ⚠  DB Password: ${DB_PASSWORD} (save this!)"

# --- Enable pgvector ---
echo ""
echo "→ Enabling pgvector extension..."
echo "  ℹ  Connect to the database and run:"
echo "     CREATE EXTENSION IF NOT EXISTS vector;"
echo "     Then run: scripts/init_db.sql"

# --- Memorystore (Redis) ---
echo ""
echo "→ Creating Memorystore Redis instance..."
REDIS_INSTANCE="research-redis"

gcloud redis instances create "${REDIS_INSTANCE}" \
    --size=1 \
    --region="${REGION}" \
    --redis-version=redis_7_0 \
    --tier=basic \
    2>/dev/null || echo "  Redis instance may already exist."

REDIS_HOST=$(gcloud redis instances describe "${REDIS_INSTANCE}" \
    --region="${REGION}" \
    --format='value(host)' 2>/dev/null || echo "pending")

echo "  ✅ Redis instance: ${REDIS_INSTANCE}"
echo "  Host: ${REDIS_HOST}"

# --- Cloud Storage Bucket ---
echo ""
echo "→ Creating Cloud Storage bucket..."
BUCKET_NAME="${PROJECT_ID}-research-uploads"
gsutil mb -l "${REGION}" "gs://${BUCKET_NAME}" 2>/dev/null || echo "  Bucket may already exist."
gsutil iam ch allUsers:objectViewer "gs://${BUCKET_NAME}" 2>/dev/null || true
echo "  ✅ Bucket: ${BUCKET_NAME}"

# --- Service Account ---
echo ""
echo "→ Creating service account..."
SA_NAME="research-backend-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="Research Backend Service Account" \
    2>/dev/null || echo "  Service account may already exist."

# Grant required roles
for role in \
    roles/cloudsql.client \
    roles/secretmanager.secretAccessor \
    roles/storage.objectAdmin \
    roles/logging.logWriter \
    roles/monitoring.metricWriter; do
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="${role}" \
        --quiet 2>/dev/null
done

echo "  ✅ Service Account: ${SA_EMAIL}"

# --- Create Secrets ---
echo ""
echo "→ Creating secrets..."
CLOUD_SQL_CONNECTION="${PROJECT_ID}:${REGION}:${INSTANCE_NAME}"
DB_URL="postgresql://postgres:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${CLOUD_SQL_CONNECTION}"
SECRET_KEY=$(openssl rand -base64 32)

echo -n "${DB_URL}" | gcloud secrets create database-url --data-file=- 2>/dev/null || \
    echo -n "${DB_URL}" | gcloud secrets versions add database-url --data-file=-

echo -n "${SECRET_KEY}" | gcloud secrets create secret-key --data-file=- 2>/dev/null || \
    echo -n "${SECRET_KEY}" | gcloud secrets versions add secret-key --data-file=-

echo -n "redis://${REDIS_HOST}:6379/0" | gcloud secrets create redis-url --data-file=- 2>/dev/null || \
    echo -n "redis://${REDIS_HOST}:6379/0" | gcloud secrets versions add redis-url --data-file=-

echo -n "redis://${REDIS_HOST}:6379/1" | gcloud secrets create celery-broker-url --data-file=- 2>/dev/null || \
    echo -n "redis://${REDIS_HOST}:6379/1" | gcloud secrets versions add celery-broker-url --data-file=-

echo "  ✅ Secrets created in Secret Manager"

echo ""
echo "============================================"
echo " ✅ Infrastructure Setup Complete!"
echo ""
echo " Next steps:"
echo " 1. Connect to Cloud SQL and run scripts/init_db.sql"
echo " 2. Run: prisma migrate deploy"
echo " 3. Deploy the app: ./gcp/deploy.sh ${PROJECT_ID} ${REGION}"
echo "============================================"
