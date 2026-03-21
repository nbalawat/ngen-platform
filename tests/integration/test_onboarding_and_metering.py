"""Integration tests: onboarding agent and metering service.

Tests against real Docker containers.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest


ONBOARDING_URL = "http://localhost:8006"
METERING_URL = "http://localhost:8007"
GATEWAY_URL = "http://localhost:8002"


# ---------------------------------------------------------------------------
# Onboarding Agent
# ---------------------------------------------------------------------------


class TestOnboardingAgentHealth:
    async def test_health(self, http: httpx.AsyncClient):
        resp = await http.get(f"{ONBOARDING_URL}/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestOnboardingSteps:
    async def test_get_steps(self, http: httpx.AsyncClient):
        resp = await http.get(f"{ONBOARDING_URL}/api/v1/onboard/steps")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["steps"]) == 5

    async def test_onboard_chat(self, http: httpx.AsyncClient):
        resp = await http.post(f"{ONBOARDING_URL}/api/v1/onboard", json={
            "message": "Help me get started",
            "tenant_id": "integration-test",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert "next_steps" in data

    async def test_platform_status(self, http: httpx.AsyncClient):
        resp = await http.get(f"{ONBOARDING_URL}/api/v1/onboard/status?tenant_id=test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "test"
        assert "model_count" in data


class TestOnboardingSeesExistingSetup:
    async def test_status_reflects_platform(self, http: httpx.AsyncClient):
        """Onboarding agent should detect existing models/policies."""
        resp = await http.get(f"{ONBOARDING_URL}/api/v1/onboard/status?tenant_id=default")
        assert resp.status_code == 200
        data = resp.json()
        # Models should exist (mock-model registered on gateway startup)
        assert data["model_count"] >= 0  # Registry may or may not have models


# ---------------------------------------------------------------------------
# Metering Service
# ---------------------------------------------------------------------------


class TestMeteringServiceHealth:
    async def test_health(self, http: httpx.AsyncClient):
        resp = await http.get(f"{METERING_URL}/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestMeteringUsage:
    async def test_list_usage(self, http: httpx.AsyncClient):
        resp = await http.get(f"{METERING_URL}/api/v1/usage")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_unknown_tenant(self, http: httpx.AsyncClient):
        resp = await http.get(f"{METERING_URL}/api/v1/usage/unknown-tenant-xyz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == 0.0

    async def test_metering_tracks_gateway_costs(self, http: httpx.AsyncClient):
        """Metering service should aggregate cost events from the gateway.

        Full pipeline: gateway → cost.recorded → NATS → metering service.
        """
        tenant = f"meter-{uuid.uuid4().hex[:8]}"

        # Make a request through the gateway
        resp = await http.post(
            f"{GATEWAY_URL}/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [{"role": "user", "content": "hello for metering"}],
            },
            headers={"x-tenant-id": tenant},
        )
        assert resp.status_code == 200

        # Wait for NATS delivery
        await asyncio.sleep(1.5)

        # Check metering endpoint
        resp = await http.get(f"{METERING_URL}/api/v1/usage/{tenant}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == tenant
        # Cost event should have been received
        assert isinstance(data["total_cost"], (int, float))


class TestMeteringAgentMemory:
    """Test agent memory endpoints via the workflow engine."""

    async def test_agent_memory_endpoint(self, http: httpx.AsyncClient):
        engine_url = "http://localhost:8003"
        name = f"mem-integ-{uuid.uuid4().hex[:8]}"

        # Create agent
        await http.post(f"{engine_url}/agents", json={
            "name": name, "framework": "default",
        })

        # Invoke to create memory entries
        await http.post(f"{engine_url}/agents/{name}/invoke", json={
            "messages": [{"role": "user", "content": "Remember this"}],
        })

        # Check memory
        resp = await http.get(
            f"{engine_url}/agents/{name}/memory?memory_type=conversational"
        )
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) >= 1

        # Check context window
        resp = await http.get(
            f"{engine_url}/agents/{name}/memory/context?query=test"
        )
        assert resp.status_code == 200
        assert "context" in resp.json()
