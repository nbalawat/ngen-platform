"""Integration test fixtures.

These tests run against real Docker Compose services. All services
must be running via:

    cd infrastructure/docker-compose && docker compose up -d

Service ports:
    tenant-service:      http://localhost:8000
    model-registry:      http://localhost:8001
    model-gateway:       http://localhost:8002
    workflow-engine:     http://localhost:8003
    governance-service:  http://localhost:8004
    mcp-manager:         http://localhost:8005
    mock-llm:            http://localhost:9100
    postgres:            localhost:5432
    redis:               localhost:6379
    nats:                localhost:4222

Run with:
    uv run pytest tests/integration/ -v --tb=short
"""

from __future__ import annotations

import httpx
import pytest


# ---------------------------------------------------------------------------
# Service URLs
# ---------------------------------------------------------------------------


SERVICE_URLS = {
    "tenant": "http://localhost:8000",
    "model_registry": "http://localhost:8001",
    "model_gateway": "http://localhost:8002",
    "workflow_engine": "http://localhost:8003",
    "governance": "http://localhost:8004",
    "mcp_manager": "http://localhost:8005",
    "mock_llm": "http://localhost:9100",
    "nats_monitor": "http://localhost:8222",
}


# ---------------------------------------------------------------------------
# Health check — skip all tests if Docker services aren't running
# ---------------------------------------------------------------------------


def _check_services_running() -> bool:
    """Quick check if key services are reachable."""
    try:
        for name in ("tenant", "model_registry", "model_gateway",
                      "workflow_engine", "governance", "mcp_manager"):
            resp = httpx.get(f"{SERVICE_URLS[name]}/health", timeout=3.0)
            if resp.status_code != 200:
                return False
        return True
    except (httpx.ConnectError, httpx.ReadTimeout):
        return False


# Skip entire module if services aren't running
pytestmark = pytest.mark.skipif(
    not _check_services_running(),
    reason="Docker Compose services not running. Start with: cd infrastructure/docker-compose && docker compose up -d",
)


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def http():
    """Shared async HTTP client for all integration tests."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest.fixture()
def tenant_url():
    return SERVICE_URLS["tenant"]


@pytest.fixture()
def registry_url():
    return SERVICE_URLS["model_registry"]


@pytest.fixture()
def gateway_url():
    return SERVICE_URLS["model_gateway"]


@pytest.fixture()
def engine_url():
    return SERVICE_URLS["workflow_engine"]


@pytest.fixture()
def governance_url():
    return SERVICE_URLS["governance"]


@pytest.fixture()
def mcp_url():
    return SERVICE_URLS["mcp_manager"]


@pytest.fixture()
def mock_llm_url():
    return SERVICE_URLS["mock_llm"]
