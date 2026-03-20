#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CLUSTER_NAME="ngen-dev"

echo "==> Creating Kind cluster '$CLUSTER_NAME'..."

if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "    Cluster '$CLUSTER_NAME' already exists. Skipping creation."
else
    kind create cluster \
        --config "$ROOT_DIR/infrastructure/kind/cluster-config.yaml" \
        --wait 120s
    echo "    Cluster created."
fi

echo "==> Installing NGINX Ingress Controller..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml 2>/dev/null || true

echo "==> Waiting for ingress controller to be ready..."
kubectl wait --namespace ingress-nginx \
    --for=condition=ready pod \
    --selector=app.kubernetes.io/component=controller \
    --timeout=120s 2>/dev/null || echo "    Ingress controller not ready yet (may take a minute)."

echo "==> Creating ngen-system namespace..."
kubectl create namespace ngen-system 2>/dev/null || true

echo "==> Cluster '$CLUSTER_NAME' is ready!"
echo "    kubectl cluster-info --context kind-${CLUSTER_NAME}"
kubectl cluster-info --context "kind-${CLUSTER_NAME}" 2>/dev/null || true
