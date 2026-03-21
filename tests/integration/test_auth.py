"""Integration tests: authentication middleware across all services.

Verifies that:
1. Without AUTH_JWT_SECRET, all endpoints are accessible (dev mode)
2. With AUTH_JWT_SECRET, endpoints require valid JWT tokens
3. Health endpoints are always excluded from auth

Tests run against the live Docker containers (dev mode — no JWT_SECRET set).
"""

from __future__ import annotations

import uuid

import httpx
import pytest


SERVICE_URLS = {
    "tenant": "http://localhost:8000",
    "model_registry": "http://localhost:8001",
    "model_gateway": "http://localhost:8002",
    "workflow_engine": "http://localhost:8003",
    "governance": "http://localhost:8004",
    "mcp_manager": "http://localhost:8005",
}


class TestHealthEndpointsAlwaysAccessible:
    """Health endpoints should work regardless of auth configuration."""

    @pytest.mark.parametrize("service,url", [
        ("tenant", SERVICE_URLS["tenant"]),
        ("model_registry", SERVICE_URLS["model_registry"]),
        ("model_gateway", SERVICE_URLS["model_gateway"]),
        ("workflow_engine", SERVICE_URLS["workflow_engine"]),
        ("governance", SERVICE_URLS["governance"]),
        ("mcp_manager", SERVICE_URLS["mcp_manager"]),
    ])
    async def test_health_always_200(self, http, service, url):
        resp = await http.get(f"{url}/health")
        assert resp.status_code == 200


class TestDevModeNoAuth:
    """Without AUTH_JWT_SECRET, all API endpoints should be accessible."""

    async def test_tenant_api_accessible(self, http):
        resp = await http.get(f"{SERVICE_URLS['tenant']}/api/v1/orgs")
        assert resp.status_code == 200

    async def test_registry_api_accessible(self, http):
        resp = await http.get(f"{SERVICE_URLS['model_registry']}/api/v1/models")
        assert resp.status_code == 200

    async def test_gateway_api_accessible(self, http):
        resp = await http.get(f"{SERVICE_URLS['model_gateway']}/v1/models")
        assert resp.status_code == 200

    async def test_workflow_api_accessible(self, http):
        resp = await http.get(f"{SERVICE_URLS['workflow_engine']}/workflows/runs")
        assert resp.status_code == 200

    async def test_governance_api_accessible(self, http):
        resp = await http.get(f"{SERVICE_URLS['governance']}/api/v1/policies")
        assert resp.status_code == 200

    async def test_mcp_api_accessible(self, http):
        resp = await http.get(f"{SERVICE_URLS['mcp_manager']}/api/v1/servers")
        assert resp.status_code == 200

    async def test_agents_api_accessible(self, http):
        resp = await http.get(f"{SERVICE_URLS['workflow_engine']}/agents")
        assert resp.status_code == 200

    async def test_budgets_api_accessible(self, http):
        resp = await http.get(f"{SERVICE_URLS['governance']}/api/v1/budgets")
        assert resp.status_code == 200


class TestAuthMiddlewareUnitLevel:
    """Unit-level tests for auth middleware — uses ASGI transport with JWT enabled."""

    @pytest.fixture()
    def jwt_secret(self):
        return "test-integration-secret-key-12345"

    @pytest.fixture()
    def _app_with_auth(self, jwt_secret):
        """Create a minimal FastAPI app with auth enabled."""
        import os
        os.environ["AUTH_JWT_SECRET"] = jwt_secret
        try:
            from fastapi import FastAPI
            from ngen_common.auth import add_auth
            from ngen_common.auth_config import make_auth_config

            app = FastAPI()

            @app.get("/health")
            async def health():
                return {"status": "ok"}

            @app.get("/api/v1/protected")
            async def protected():
                return {"message": "secret data"}

            add_auth(app, make_auth_config())
            yield app
        finally:
            del os.environ["AUTH_JWT_SECRET"]

    @pytest.fixture()
    async def auth_client(self, _app_with_auth):
        transport = httpx.ASGITransport(app=_app_with_auth)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as c:
            yield c

    async def test_health_excluded(self, auth_client):
        resp = await auth_client.get("/health")
        assert resp.status_code == 200

    async def test_protected_requires_auth(self, auth_client):
        resp = await auth_client.get("/api/v1/protected")
        assert resp.status_code == 401

    async def test_valid_jwt_grants_access(self, auth_client, jwt_secret):
        from ngen_common.auth import create_jwt
        token = create_jwt(
            jwt_secret, subject="user-1", tenant_id="acme", roles=["admin"],
        )
        resp = await auth_client.get(
            "/api/v1/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "secret data"

    async def test_invalid_jwt_rejected(self, auth_client):
        resp = await auth_client.get(
            "/api/v1/protected",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    async def test_expired_jwt_rejected(self, auth_client, jwt_secret):
        from ngen_common.auth import create_jwt
        token = create_jwt(
            jwt_secret, subject="user-1", expires_in=-120,  # expired 2 minutes ago (beyond 30s skew tolerance)
        )
        resp = await auth_client.get(
            "/api/v1/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
