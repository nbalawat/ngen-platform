"""Multi-tenant isolation tests — prove tenants cannot see each other's resources."""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
import pytest

from ngen_common.auth import create_jwt

# JWT secret — must match what the app uses
JWT_SECRET = "test-isolation-secret"


@pytest.fixture(autouse=True)
def _enable_jwt_auth(monkeypatch):
    """Enable JWT auth for these tests by setting the env var."""
    monkeypatch.setenv("AUTH_JWT_SECRET", JWT_SECRET)


@pytest.fixture()
def app(executor, settings):
    """Override app fixture to pick up JWT auth config."""
    from workflow_engine.app import create_app
    return create_app(executor=executor, settings=settings, default_framework="in-memory")


@pytest.fixture()
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://workflow-engine"
    ) as ac:
        yield ac


def _token(tenant_id: str, subject: str = "test-user", roles: list[str] | None = None) -> str:
    return create_jwt(
        secret=JWT_SECRET,
        subject=subject,
        tenant_id=tenant_id,
        roles=roles or ["admin"],
        expires_in=3600,
    )


TOKEN_ALPHA = _token("tenant-alpha", "user-alpha")
TOKEN_BETA = _token("tenant-beta", "user-beta")


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _alpha_headers() -> dict[str, str]:
    return _headers(TOKEN_ALPHA)


def _beta_headers() -> dict[str, str]:
    return _headers(TOKEN_BETA)


class TestAgentIsolation:
    """Agents created by one tenant must be invisible to another."""

    async def test_tenant_a_agents_invisible_to_tenant_b(self, client: httpx.AsyncClient):
        """Create an agent as tenant-alpha, list as tenant-beta → empty."""
        # Create agent as tenant-alpha
        resp = await client.post(
            "/agents",
            headers=_alpha_headers(),
            json={
                "name": "alpha-research-bot",
                "framework": "in-memory",
                "description": "Alpha's private agent",
                "system_prompt": "You are alpha's agent.",
            },
        )
        assert resp.status_code == 201

        # List as tenant-beta → should NOT see alpha's agent
        resp = await client.get("/agents", headers=_beta_headers())
        assert resp.status_code == 200
        beta_agents = resp.json()
        agent_names = [a["name"] for a in beta_agents]
        assert "alpha-research-bot" not in agent_names

        # List as tenant-alpha → SHOULD see the agent
        resp = await client.get("/agents", headers=_alpha_headers())
        alpha_agents = resp.json()
        agent_names = [a["name"] for a in alpha_agents]
        assert "alpha-research-bot" in agent_names

    async def test_tenant_b_cannot_get_tenant_a_agent(self, client: httpx.AsyncClient):
        """Direct GET of tenant-alpha's agent as tenant-beta → 404."""
        # Create as alpha
        await client.post(
            "/agents",
            headers=_alpha_headers(),
            json={"name": "alpha-secret", "framework": "in-memory"},
        )

        # GET as beta → 404
        resp = await client.get("/agents/alpha-secret", headers=_beta_headers())
        assert resp.status_code == 404

    async def test_same_agent_name_different_tenants(self, client: httpx.AsyncClient):
        """Two tenants can create agents with the same name without collision."""
        # Alpha creates "shared-name"
        resp = await client.post(
            "/agents",
            headers=_alpha_headers(),
            json={
                "name": "shared-name",
                "framework": "in-memory",
                "description": "Alpha's version",
                "system_prompt": "I am alpha.",
            },
        )
        assert resp.status_code == 201

        # Beta creates "shared-name" → should NOT conflict
        resp = await client.post(
            "/agents",
            headers=_beta_headers(),
            json={
                "name": "shared-name",
                "framework": "in-memory",
                "description": "Beta's version",
                "system_prompt": "I am beta.",
            },
        )
        assert resp.status_code == 201

        # Each tenant sees their own version
        resp = await client.get("/agents/shared-name", headers=_alpha_headers())
        assert resp.json()["description"] == "Alpha's version"

        resp = await client.get("/agents/shared-name", headers=_beta_headers())
        assert resp.json()["description"] == "Beta's version"

    async def test_tenant_a_cannot_invoke_tenant_b_agent(self, client: httpx.AsyncClient):
        """Invoking another tenant's agent returns 404."""
        # Create as beta
        await client.post(
            "/agents",
            headers=_beta_headers(),
            json={"name": "beta-bot", "framework": "in-memory"},
        )

        # Invoke as alpha → 404
        resp = await client.post(
            "/agents/beta-bot/invoke",
            headers=_alpha_headers(),
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        assert resp.status_code == 404

    async def test_tenant_a_cannot_delete_tenant_b_agent(self, client: httpx.AsyncClient):
        """Deleting another tenant's agent returns 404."""
        # Create as beta
        await client.post(
            "/agents",
            headers=_beta_headers(),
            json={"name": "beta-precious", "framework": "in-memory"},
        )

        # Delete as alpha → 404
        resp = await client.delete("/agents/beta-precious", headers=_alpha_headers())
        assert resp.status_code == 404

        # Beta can still see it
        resp = await client.get("/agents/beta-precious", headers=_beta_headers())
        assert resp.status_code == 200


class TestTenantFallback:
    """When JWT auth is enabled, unauthenticated requests are rejected."""

    async def test_no_auth_header_rejected(self, client: httpx.AsyncClient):
        """Requests without auth token should be rejected (401)."""
        resp = await client.post(
            "/agents",
            json={"name": "no-auth-agent", "framework": "in-memory"},
        )
        assert resp.status_code == 401

    async def test_x_tenant_id_header_works_with_jwt(self, client: httpx.AsyncClient):
        """JWT tenant_id takes priority over x-tenant-id header."""
        # Create with JWT (tenant_id=tenant-alpha) + conflicting x-tenant-id header
        resp = await client.post(
            "/agents",
            headers={
                **_alpha_headers(),
                "x-tenant-id": "wrong-tenant",
            },
            json={"name": "jwt-wins", "framework": "in-memory"},
        )
        assert resp.status_code == 201

        # JWT tenant (alpha) can see it
        resp = await client.get("/agents/jwt-wins", headers=_alpha_headers())
        assert resp.status_code == 200

        # The x-tenant-id header tenant cannot
        resp = await client.get("/agents/jwt-wins", headers=_beta_headers())
        assert resp.status_code == 404


class TestCrossTenantCounts:
    """Each tenant's agent count is independent."""

    async def test_independent_agent_counts(self, client: httpx.AsyncClient):
        """Creating agents in one tenant doesn't affect another's count."""
        # Create 3 agents for alpha
        for i in range(3):
            await client.post(
                "/agents",
                headers=_alpha_headers(),
                json={"name": f"alpha-agent-{i}", "framework": "in-memory"},
            )

        # Create 1 agent for beta
        await client.post(
            "/agents",
            headers=_beta_headers(),
            json={"name": "beta-only", "framework": "in-memory"},
        )

        # Alpha sees 3
        resp = await client.get("/agents", headers=_alpha_headers())
        assert len(resp.json()) == 3

        # Beta sees 1
        resp = await client.get("/agents", headers=_beta_headers())
        assert len(resp.json()) == 1
