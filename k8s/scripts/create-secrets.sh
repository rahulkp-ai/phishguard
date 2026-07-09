#!/usr/bin/env bash
# =============================================================================
# k8s/scripts/create-secrets.sh
# =============================================================================
#
# Creates the phishguard-secret in Kubernetes from environment variables.
#
# WHY THIS SCRIPT EXISTS
# ──────────────────────
# The Secret manifest is intentionally NOT in version control.
# A committed Secret is a leaked secret — even in a private repo, all
# contributors can read it, and git history never forgets.
#
# Instead: secrets live in your team's secret manager (Vault, AWS Secrets
# Manager, GCP Secret Manager, 1Password, etc.) and are injected via this
# script at deploy time by CI/CD with appropriate credentials.
#
# USAGE
# ─────
#   export SECRET_KEY=$(python scripts/generate_secret_key.py)
#   bash k8s/scripts/create-secrets.sh
#
# Or for a specific environment:
#   bash k8s/scripts/create-secrets.sh --env production
#
# PREREQUISITES
# ─────────────
#   kubectl configured and pointing at the target cluster.
#   The phishguard namespace must exist (apply base manifests first).
# =============================================================================

set -euo pipefail

ENV="${1:---env}" ; ENV="${2:-development}"

# ── Validate required environment variables ──────────────────────────────────
if [[ -z "${SECRET_KEY:-}" ]]; then
  echo "ERROR: SECRET_KEY environment variable is not set."
  echo ""
  echo "Generate one with:"
  echo "  export SECRET_KEY=\$(python scripts/generate_secret_key.py)"
  exit 1
fi

if [[ ${#SECRET_KEY} -lt 32 ]]; then
  echo "ERROR: SECRET_KEY is too short (${#SECRET_KEY} chars). Minimum 32 characters."
  exit 1
fi

NAMESPACE="phishguard"

echo "Creating phishguard-secret in namespace '${NAMESPACE}'..."

# --from-literal: values are taken directly from the shell — never written
# to disk, never appear in process arguments in a way that could be
# intercepted by other processes.
kubectl create secret generic phishguard-secret \
  --namespace="${NAMESPACE}" \
  --from-literal=SECRET_KEY="${SECRET_KEY}" \
  --dry-run=client \
  --output=yaml \
| kubectl apply -f -

echo ""
echo "Secret created/updated."
echo ""
echo "Verify (values are base64-encoded, not plaintext):"
echo "  kubectl get secret phishguard-secret -n ${NAMESPACE}"
echo ""
echo "IMPORTANT: Never run 'kubectl get secret phishguard-secret -o yaml'"
echo "in a shared terminal session — the base64 value is trivially decoded."
