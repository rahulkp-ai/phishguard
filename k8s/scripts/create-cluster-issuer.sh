#!/usr/bin/env bash
# =============================================================================
# k8s/scripts/create-cluster-issuer.sh
# =============================================================================
# Creates cert-manager ClusterIssuers for Let's Encrypt (staging + prod).
# Run once per cluster after cert-manager is installed.
#
# Usage:
#   export ACME_EMAIL=your-email@domain.com
#   bash k8s/scripts/create-cluster-issuer.sh
# =============================================================================

set -euo pipefail

ACME_EMAIL="${ACME_EMAIL:?Set ACME_EMAIL to your Let's Encrypt registration email}"

cat <<EOF | kubectl apply -f -
---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-staging
spec:
  acme:
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    email: ${ACME_EMAIL}
    privateKeySecretRef:
      name: letsencrypt-staging-key
    solvers:
      - http01:
          ingress:
            class: nginx
---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ${ACME_EMAIL}
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
      - http01:
          ingress:
            class: nginx
EOF

echo "ClusterIssuers created. Verify with:"
echo "  kubectl get clusterissuer"
