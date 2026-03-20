#!/usr/bin/env bash
set -euo pipefail

echo "============================================"
echo "  NGEN Platform - Bootstrap"
echo "============================================"
echo ""

# Check prerequisites
echo "==> Checking prerequisites..."

check_cmd() {
    if ! command -v "$1" &>/dev/null; then
        echo "ERROR: $1 is required but not installed."
        echo "  $2"
        exit 1
    fi
    echo "  ✓ $1 found: $($1 --version 2>&1 | head -1)"
}

check_cmd "python3" "Install Python 3.11+: https://python.org"
check_cmd "docker" "Install Docker: https://docker.com"

# Check for uv, install if missing
if ! command -v uv &>/dev/null; then
    echo "  → Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
check_cmd "uv" "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"

echo ""
echo "==> Installing dependencies..."
make install

echo ""
echo "==> Running linters..."
make lint || {
    echo "  → Fixing lint issues..."
    make lint-fix
}

echo ""
echo "==> Running tests..."
make test

echo ""
echo "============================================"
echo "  Bootstrap complete!"
echo ""
echo "  Next steps:"
echo "    make infra-up     # Start PostgreSQL, Redis, NATS"
echo "    make test-all     # Run all tests"
echo "    make kind-up      # Create Kind K8s cluster"
echo "============================================"
