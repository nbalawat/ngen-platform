#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="ngen-dev"

echo "==> Deleting Kind cluster '$CLUSTER_NAME'..."
kind delete cluster --name "$CLUSTER_NAME" 2>/dev/null || echo "    Cluster '$CLUSTER_NAME' not found."
echo "==> Done."
