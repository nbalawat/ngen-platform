"""Integration tests: health checks, observability, and metrics.

Verifies every service is healthy, returns proper headers, and
exposes a /metrics endpoint.
"""

from __future__ import annotations

import httpx
import pytest

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
# Health checks — every service must respond on /health
# ---------------------------------------------------------------------------


class TestHealthChecks:
    """Every service must return 200 on /health with a status field."""

    @pytest.mark.parametrize("service,url", [
        ("tenant-service", SERVICE_URLS["tenant"]),
        ("model-registry", SERVICE_URLS["model_registry"]),
        ("model-gateway", SERVICE_URLS["model_gateway"]),
        ("workflow-engine", SERVICE_URLS["workflow_engine"]),
        ("governance-service", SERVICE_URLS["governance"]),
        ("mcp-manager", SERVICE_URLS["mcp_manager"]),
        ("mock-llm", SERVICE_URLS["mock_llm"]),
    ])
    async def test_health_endpoint(self, http: httpx.AsyncClient, service, url):
        resp = await http.get(f"{url}/health")
        assert resp.status_code == 200, f"{service} health check failed: {resp.text}"
        data = resp.json()
        assert "status" in data, f"{service} health missing 'status' field"


# ---------------------------------------------------------------------------
# Observability — correlation IDs and metrics
# ---------------------------------------------------------------------------


class TestObservability:
    """Verify correlation ID propagation and metrics endpoints."""

    @pytest.mark.parametrize("service,url", [
        ("model-registry", SERVICE_URLS["model_registry"]),
        ("governance-service", SERVICE_URLS["governance"]),
        ("mcp-manager", SERVICE_URLS["mcp_manager"]),
    ])
    async def test_request_id_propagated(self, http: httpx.AsyncClient, service, url):
        """Services must echo back X-Request-ID in response headers."""
        resp = await http.get(
            f"{url}/health",
            headers={"X-Request-ID": f"integ-test-{service}"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("x-request-id") == f"integ-test-{service}", \
            f"{service} did not propagate X-Request-ID"

    @pytest.mark.parametrize("service,url", [
        ("model-registry", SERVICE_URLS["model_registry"]),
        ("governance-service", SERVICE_URLS["governance"]),
        ("mcp-manager", SERVICE_URLS["mcp_manager"]),
    ])
    async def test_metrics_endpoint(self, http: httpx.AsyncClient, service, url):
        """Services must expose /metrics with summary and routes."""
        resp = await http.get(f"{url}/metrics")
        assert resp.status_code == 200, f"{service} /metrics failed"
        data = resp.json()
        assert "summary" in data, f"{service} /metrics missing summary"
        assert "routes" in data, f"{service} /metrics missing routes"
        assert data["summary"]["total_requests"] >= 0

    @pytest.mark.parametrize("service,url", [
        ("model-registry", SERVICE_URLS["model_registry"]),
        ("governance-service", SERVICE_URLS["governance"]),
        ("mcp-manager", SERVICE_URLS["mcp_manager"]),
    ])
    async def test_server_timing_header(self, http: httpx.AsyncClient, service, url):
        """Services should return Server-Timing header for latency tracking."""
        resp = await http.get(f"{url}/health")
        timing = resp.headers.get("server-timing")
        assert timing is not None, f"{service} missing Server-Timing header"
        assert "dur=" in timing


# ---------------------------------------------------------------------------
# Infrastructure — NATS and Redis
# ---------------------------------------------------------------------------


class TestInfrastructure:
    """Verify infrastructure services are reachable."""

    async def test_nats_monitoring(self, http: httpx.AsyncClient):
        """NATS monitoring endpoint should be available."""
        resp = await http.get(f"{SERVICE_URLS['nats_monitor']}/varz")
        assert resp.status_code == 200
        data = resp.json()
        assert "server_id" in data

    async def test_nats_healthz(self, http: httpx.AsyncClient):
        resp = await http.get(f"{SERVICE_URLS['nats_monitor']}/healthz")
        assert resp.status_code == 200

    async def test_mock_llm_models(self, http: httpx.AsyncClient):
        """Mock LLM should list available models."""
        resp = await http.get(f"{SERVICE_URLS['mock_llm']}/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data.get("data", [])) > 0
