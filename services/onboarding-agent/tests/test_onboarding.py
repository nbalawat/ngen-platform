"""Tests for the onboarding agent service.

Uses ASGI transport. No mocks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from onboarding_agent.app import create_app


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://onboarding"
    ) as c:
        yield c


class TestHealth:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestOnboardingSteps:
    async def test_get_steps(self, client):
        resp = await client.get("/api/v1/onboard/steps")
        assert resp.status_code == 200
        data = resp.json()
        assert "steps" in data
        assert len(data["steps"]) == 5

    async def test_steps_include_key_items(self, client):
        resp = await client.get("/api/v1/onboard/steps")
        steps = resp.json()["steps"]
        steps_text = " ".join(steps).lower()
        assert "organization" in steps_text
        assert "model" in steps_text
        assert "governance" in steps_text
        assert "workflow" in steps_text


class TestOnboardingChat:
    async def test_onboard_returns_response(self, client):
        resp = await client.post("/api/v1/onboard", json={
            "message": "Help me get started",
            "tenant_id": "test-tenant",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert "next_steps" in data
        assert isinstance(data["next_steps"], list)

    async def test_onboard_provides_next_steps(self, client):
        resp = await client.post("/api/v1/onboard", json={
            "message": "What should I do?",
        })
        data = resp.json()
        # Without any platform setup, should suggest all steps
        assert len(data["next_steps"]) > 0


class TestPlatformStatus:
    async def test_status_endpoint(self, client):
        resp = await client.get("/api/v1/onboard/status?tenant_id=test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "test"
        assert "model_count" in data
        assert "policy_count" in data
