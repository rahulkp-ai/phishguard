#!/usr/bin/env bash
# =============================================================================
# k8s/scripts/deploy.sh — deploy PhishGuard to a kustomize overlay
# =============================================================================
#
# Usage
# ─────
#   bash k8s/scripts/deploy.sh <overlay> <image-tag>
#
# Examples
#   bash k8s/scripts/deploy.sh dev dev
#   bash k8s/scripts/deploy.sh staging sha-abc1234
#   bash k8s/scripts/deploy.sh production sha-abc1234
#
# What this script does
# ──────────────────────
# 1. Validates prerequisites (kubectl, kustomize).
# 2. Pins the image tag in the overlay's kustomization.yaml.
# 3. Updates the configmap checksum annotation so pods restart if config changed.
# 4. Runs `kubectl apply -k` to apply the overlay.
# 5. Waits for the rollout to complete (`kubectl rollout status`).
# 6. Runs a post-deploy smoke test against /api/health.
# 7. On failure, automatically rolls back with `kubectl rollout undo`.
#
# CI/CD usage (GitHub Actions)
# ─────────────────────────────
# The docker-publish.yml workflow outputs the image digest.
# The CI/CD deployment step calls this script with that digest:
#   bash k8s/scripts/deploy.sh production sha-${{ steps.meta.outputs.version }}
# =============================================================================

set -euo pipefail

# ── Arguments ────────────────────────────────────────────────────────────────
OVERLAY="${1:?Usage: deploy.sh <overlay> <image-tag>}"
IMAGE_TAG="${2:?Usage: deploy.sh <overlay> <image-tag>}"

NAMESPACE="phishguard"
IMAGE_REPO="ghcr.io/YOUR_GITHUB_USERNAME/phishguard"
OVERLAY_DIR="k8s/overlays/${OVERLAY}"
ROLLOUT_TIMEOUT="300s"   # 5 minutes

# ── Colour output ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[deploy]${NC} $*"; }
warning() { echo -e "${YELLOW}[deploy]${NC} $*"; }
error()   { echo -e "${RED}[deploy]${NC} $*" >&2; }

# ── Validate prerequisites ────────────────────────────────────────────────────
info "Checking prerequisites..."

if ! command -v kubectl &>/dev/null; then
  error "kubectl not found. Install: https://kubernetes.io/docs/tasks/tools/"
  exit 1
fi

if ! command -v kustomize &>/dev/null; then
  error "kustomize not found. Install: https://kubectl.docs.kubernetes.io/installation/kustomize/"
  exit 1
fi

if [[ ! -d "${OVERLAY_DIR}" ]]; then
  error "Overlay directory not found: ${OVERLAY_DIR}"
  exit 1
fi

info "Deploying overlay='${OVERLAY}' image='${IMAGE_REPO}:${IMAGE_TAG}'"

# ── Pin image tag ─────────────────────────────────────────────────────────────
info "Pinning image tag in kustomization..."
pushd "${OVERLAY_DIR}" > /dev/null
kustomize edit set image "${IMAGE_REPO}:${IMAGE_TAG}"
popd > /dev/null

# ── Update configmap checksum annotation ─────────────────────────────────────
# Forces pod restart if ConfigMap content has changed since last deploy.
info "Computing ConfigMap checksum..."
CHECKSUM=$(kubectl create configmap phishguard-config \
  --from-env-file=<(cat k8s/base/configmap.yaml | grep "  " | grep ": " | sed 's/: /=/;s/^  //') \
  --dry-run=client -o yaml 2>/dev/null | sha256sum | cut -d' ' -f1 || echo "unknown")

# Patch the deployment annotation (best-effort — doesn't fail deploy if it errors)
kubectl patch deployment phishguard \
  -n "${NAMESPACE}" \
  --type=json \
  -p="[{\"op\":\"replace\",\"path\":\"/spec/template/metadata/annotations/checksum~1config\",\"value\":\"${CHECKSUM}\"}]" \
  2>/dev/null || warning "Could not update checksum annotation (deployment may not exist yet)"

# ── Apply manifests ───────────────────────────────────────────────────────────
info "Applying kustomize overlay: ${OVERLAY_DIR}"
kubectl apply -k "${OVERLAY_DIR}"

# ── Wait for rollout ──────────────────────────────────────────────────────────
info "Waiting for rollout to complete (timeout: ${ROLLOUT_TIMEOUT})..."
if ! kubectl rollout status deployment/phishguard \
     -n "${NAMESPACE}" \
     --timeout="${ROLLOUT_TIMEOUT}"; then

  error "Rollout failed! Rolling back..."
  kubectl rollout undo deployment/phishguard -n "${NAMESPACE}"

  error "Rollback initiated. Check pod logs:"
  echo "  kubectl logs -l app.kubernetes.io/name=phishguard -n ${NAMESPACE} --previous"
  exit 1
fi

# ── Smoke test ────────────────────────────────────────────────────────────────
info "Running post-deploy smoke test..."

# Use port-forward for smoke test (works regardless of Ingress)
kubectl port-forward svc/phishguard 18080:80 -n "${NAMESPACE}" &
PF_PID=$!
sleep 3    # give port-forward a moment to establish

cleanup() { kill "${PF_PID}" 2>/dev/null || true; }
trap cleanup EXIT

HEALTH=$(curl --fail --silent --max-time 10 http://localhost:18080/api/health 2>/dev/null || echo '{"status":"unreachable"}')
STATUS=$(echo "${HEALTH}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "parse-error")

if [[ "${STATUS}" == "ok" ]]; then
  info "Smoke test passed: status=${STATUS}"
elif [[ "${STATUS}" == "degraded" ]]; then
  warning "Smoke test: status=degraded (model not yet loaded — run the training job)"
else
  error "Smoke test FAILED: status=${STATUS}"
  error "Raw response: ${HEALTH}"
  error "Rolling back..."
  kill "${PF_PID}" 2>/dev/null || true
  kubectl rollout undo deployment/phishguard -n "${NAMESPACE}"
  exit 1
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
info "Deployment complete."
echo ""
echo "  Overlay  : ${OVERLAY}"
echo "  Image    : ${IMAGE_REPO}:${IMAGE_TAG}"
echo "  Pods     :"
kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=phishguard \
  --no-headers -o custom-columns="    NAME:.metadata.name,STATUS:.status.phase,READY:.status.containerStatuses[0].ready"
echo ""
echo "  View logs:"
echo "    kubectl logs -l app.kubernetes.io/name=phishguard -n ${NAMESPACE} -f"
echo ""
echo "  Run predictions:"
echo "    kubectl port-forward svc/phishguard 5000:80 -n ${NAMESPACE}"
echo "    curl -X POST http://localhost:5000/api/predict -H 'Content-Type: application/json' -d '{\"url\":\"https://google.com\"}'"
