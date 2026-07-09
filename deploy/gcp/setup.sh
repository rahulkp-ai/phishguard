#!/usr/bin/env bash
# =============================================================================
# deploy/gcp/setup.sh — one-time GCP project setup for PhishGuard
# =============================================================================
#
# Run this ONCE per GCP project. After this, pushes to main auto-deploy.
#
# Prerequisites:
#   1. Google Cloud account (free tier — card required but not charged)
#   2. gcloud CLI installed: https://cloud.google.com/sdk/docs/install
#   3. A GCP project created at console.cloud.google.com
#
# Usage:
#   export GCP_PROJECT_ID=your-project-id
#   export GITHUB_USERNAME=rahulkp-ai
#   export GITHUB_REPO=phishing-detection
#   bash deploy/gcp/setup.sh
#
# What this creates (all on free tier):
#   - Artifact Registry repo (stores Docker images, 0.5 GB free)
#   - Secret Manager secret (stores SECRET_KEY, 6 active secret versions free)
#   - Cloud Build trigger (builds on push to main, 120 min/day free)
#   - Cloud Run service (2M requests/month free in us-central1)
# =============================================================================

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
GITHUB_USERNAME="${GITHUB_USERNAME:?Set GITHUB_USERNAME}"
GITHUB_REPO="${GITHUB_REPO:-phishing-detection}"
REGION="us-central1"          # MUST be us-central1 for free tier
REPO_NAME="phishguard"
SERVICE_NAME="phishguard"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
step() { echo -e "\n${CYAN}▶ $*${NC}"; }
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }

# ── Set active project ────────────────────────────────────────────────────────
step "Setting active project: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"
ok "Project set"

# ── Enable required APIs ──────────────────────────────────────────────────────
step "Enabling required GCP APIs (this takes ~2 min on first run)..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  --quiet
ok "APIs enabled"

# ── Create Artifact Registry repository ──────────────────────────────────────
step "Creating Artifact Registry repository: $REPO_NAME"
if gcloud artifacts repositories describe "$REPO_NAME" \
     --location="$REGION" &>/dev/null; then
  warn "Repository '$REPO_NAME' already exists — skipping"
else
  gcloud artifacts repositories create "$REPO_NAME" \
    --repository-format=docker \
    --location="$REGION" \
    --description="PhishGuard Docker images" \
    --quiet
  ok "Repository created: ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"
fi

# ── Authenticate Docker with Artifact Registry ────────────────────────────────
step "Configuring Docker authentication for Artifact Registry"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
ok "Docker configured"

# ── Create SECRET_KEY in Secret Manager ──────────────────────────────────────
step "Creating SECRET_KEY in Secret Manager"
SECRET_KEY=$(python3 scripts/generate_secret_key.py)

if gcloud secrets describe phishguard-secret-key &>/dev/null; then
  warn "Secret 'phishguard-secret-key' already exists — adding new version"
  echo -n "$SECRET_KEY" | gcloud secrets versions add phishguard-secret-key --data-file=-
else
  echo -n "$SECRET_KEY" | gcloud secrets create phishguard-secret-key \
    --data-file=- \
    --replication-policy=automatic \
    --quiet
fi
ok "Secret created/updated in Secret Manager"
echo "  (The actual value is stored securely — you don't need to save it)"

# ── Grant Cloud Build access to Secret Manager ────────────────────────────────
step "Granting Cloud Build service account access to secrets"
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
CLOUD_BUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet > /dev/null

# Also grant Cloud Build the ability to deploy to Cloud Run
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/run.admin" \
  --quiet > /dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${CLOUD_BUILD_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --quiet > /dev/null

ok "IAM permissions granted"

# ── Create Cloud Build trigger ────────────────────────────────────────────────
step "Creating Cloud Build trigger (push to main → auto deploy)"
warn "This step requires connecting your GitHub repo in the Cloud Console."
echo ""
echo "  Complete these steps in your browser:"
echo ""
echo "  1. Open: https://console.cloud.google.com/cloud-build/triggers/connect"
echo "     Project: $PROJECT_ID"
echo ""
echo "  2. Select 'GitHub (Cloud Build GitHub App)'"
echo "  3. Authenticate and select: $GITHUB_USERNAME/$GITHUB_REPO"
echo ""
echo "  4. After connecting, run this command to create the trigger:"
echo ""
echo -e "     ${YELLOW}gcloud builds triggers create github \\"
echo "       --repo-name=$GITHUB_REPO \\"
echo "       --repo-owner=$GITHUB_USERNAME \\"
echo "       --branch-pattern='^main$' \\"
echo "       --build-config=deploy/gcp/cloudbuild.yaml \\"
echo "       --name=phishguard-main \\"
echo -e "       --project=$PROJECT_ID${NC}"
echo ""

# ── Initial manual deploy ─────────────────────────────────────────────────────
step "Running initial deployment (builds + trains + deploys)..."
echo ""
echo "  This will take ~12 minutes on first run (downloads data + trains model)."
echo "  Press Ctrl+C to skip and trigger via git push to main instead."
echo ""
read -rp "  Run initial deploy now? [y/N] " CONFIRM
if [[ "${CONFIRM,,}" == "y" ]]; then
  gcloud builds submit \
    --config=deploy/gcp/cloudbuild.yaml \
    --project="$PROJECT_ID" \
    --substitutions="_REGION=${REGION},_REPO=${REPO_NAME}" \
    .
  ok "Initial deploy complete"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN} GCP Setup Complete${NC}"
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo ""
echo "  Project      : $PROJECT_ID"
echo "  Region       : $REGION (free tier)"
echo "  Image repo   : ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"
echo "  Service name : $SERVICE_NAME"
echo ""
echo "  After first deploy, get your URL:"
echo "    gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)'"
echo ""
echo "  Free tier monthly limits:"
echo "    Cloud Run   : 2,000,000 requests    ← your entire portfolio traffic"
echo "    Cloud Build : 120 build-minutes/day ← ~10 deploys/day"
echo "    Artifact Reg: 0.5 GB image storage  ← 5–6 full images"
echo "    Secret Mgr  : 6 secret versions     ← more than enough"
echo ""
echo "  Monthly cost at portfolio scale: \$0.00"
