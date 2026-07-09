#!/usr/bin/env bash
# =============================================================================
# deploy/gcp/setup-wif.sh — Workload Identity Federation setup
# =============================================================================
#
# Run this ONCE. It creates the WIF pool + provider that lets GitHub Actions
# authenticate to GCP without storing a service account key JSON anywhere.
#
# Why WIF instead of a service account key?
# ──────────────────────────────────────────
# A service account key is a long-lived credential — if it leaks from GitHub
# Secrets, an attacker has permanent GCP access until you manually rotate it.
# WIF uses short-lived OIDC tokens: GitHub generates a token per-workflow-run
# that GCP exchanges for a short-lived access token. No key to leak.
# Google explicitly recommends this over service account keys.
#
# Usage:
#   export GCP_PROJECT_ID=your-project-id
#   export GITHUB_USERNAME=rahulkp-ai
#   export GITHUB_REPO=phishing-detection
#   bash deploy/gcp/setup-wif.sh
#
# Output: three values to add as GitHub Secrets.
# =============================================================================

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
GITHUB_USERNAME="${GITHUB_USERNAME:?Set GITHUB_USERNAME}"
GITHUB_REPO="${GITHUB_REPO:-phishing-detection}"

POOL_ID="github-actions-pool"
PROVIDER_ID="github-provider"
SA_NAME="phishguard-deployer"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
step() { echo -e "\n${CYAN}▶ $*${NC}"; }
ok()   { echo -e "${GREEN}✓ $*${NC}"; }

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")

# ── Create service account ────────────────────────────────────────────────────
step "Creating service account: $SA_NAME"
if gcloud iam service-accounts describe \
     "${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" &>/dev/null; then
  ok "Service account already exists"
else
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="PhishGuard GitHub Actions Deployer" \
    --project="$PROJECT_ID"
  ok "Service account created"
fi

SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant required roles
for ROLE in \
  roles/run.admin \
  roles/artifactregistry.writer \
  roles/secretmanager.secretAccessor \
  roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE" \
    --quiet > /dev/null
done
ok "IAM roles granted to service account"

# ── Create Workload Identity Pool ─────────────────────────────────────────────
step "Creating Workload Identity Pool: $POOL_ID"
if gcloud iam workload-identity-pools describe "$POOL_ID" \
     --location=global &>/dev/null; then
  ok "Pool already exists"
else
  gcloud iam workload-identity-pools create "$POOL_ID" \
    --location=global \
    --display-name="GitHub Actions Pool" \
    --quiet
  ok "Pool created"
fi

# ── Create OIDC Provider ──────────────────────────────────────────────────────
step "Creating OIDC Provider: $PROVIDER_ID"
if gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
     --workload-identity-pool="$POOL_ID" \
     --location=global &>/dev/null; then
  ok "Provider already exists"
else
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
    --workload-identity-pool="$POOL_ID" \
    --location=global \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='${GITHUB_USERNAME}/${GITHUB_REPO}'" \
    --quiet
  ok "Provider created"
fi

# ── Bind service account to WIF pool ─────────────────────────────────────────
step "Binding service account to WIF pool (repo: ${GITHUB_USERNAME}/${GITHUB_REPO})"
WORKLOAD_IDENTITY_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}"

gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${GITHUB_USERNAME}/${GITHUB_REPO}" \
  --quiet > /dev/null
ok "Service account bound to WIF pool"

# ── Output GitHub Secrets ─────────────────────────────────────────────────────
WIF_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}"

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN} Workload Identity Federation setup complete${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Add these three secrets to your GitHub repo:"
echo "  Settings → Secrets and variables → Actions → New repository secret"
echo ""
echo -e "${YELLOW}Secret 1:${NC}"
echo "  Name:  GCP_PROJECT_ID"
echo "  Value: $PROJECT_ID"
echo ""
echo -e "${YELLOW}Secret 2:${NC}"
echo "  Name:  GCP_WORKLOAD_IDENTITY"
echo "  Value: $WIF_PROVIDER"
echo ""
echo -e "${YELLOW}Secret 3:${NC}"
echo "  Name:  GCP_SERVICE_ACCOUNT"
echo "  Value: $SA_EMAIL"
echo ""
echo "After adding the secrets, push to main to trigger your first deploy."
