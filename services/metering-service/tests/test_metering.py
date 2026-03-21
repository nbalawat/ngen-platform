"""Tests for the metering service — usage aggregation from cost events.

Uses InMemoryEventBus. No mocks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from metering_service.app import UsageTracker, create_app
from ngen_common.events import InMemoryEventBus


@pytest.fixture()
def bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture()
def tracker() -> UsageTracker:
    return UsageTracker()


@pytest.fixture()
def app(tracker, bus):
    application = create_app(usage_tracker=tracker)
    application.state.event_bus = bus
    return application


@pytest.fixture()
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://metering"
    ) as c:
        yield c


class TestUsageTracking:
    async def test_tracks_single_event(self, bus, tracker):
        await tracker.start(bus)
        await bus.publish("cost.recorded", {
            "tenant_id": "acme",
            "model": "claude-sonnet",
            "total_cost": 0.05,
            "total_tokens": 1500,
        })

        usage = tracker.get_tenant("acme")
        assert usage is not None
        assert usage.total_cost == 0.05
        assert usage.total_tokens == 1500
        assert usage.total_requests == 1
        await tracker.stop(bus)

    async def test_accumulates_across_tenants(self, bus, tracker):
        await tracker.start(bus)
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 0.10, "total_tokens": 1000,
        })
        await bus.publish("cost.recorded", {
            "tenant_id": "globex", "model": "test",
            "total_cost": 0.20, "total_tokens": 2000,
        })

        tenants = tracker.list_tenants()
        assert len(tenants) == 2
        await tracker.stop(bus)

    async def test_tracks_per_model_cost(self, bus, tracker):
        await tracker.start(bus)
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "claude-sonnet",
            "total_cost": 0.05, "total_tokens": 1000,
        })
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "claude-haiku",
            "total_cost": 0.01, "total_tokens": 500,
        })

        usage = tracker.get_tenant("acme")
        assert usage.models["claude-sonnet"] == pytest.approx(0.05)
        assert usage.models["claude-haiku"] == pytest.approx(0.01)
        await tracker.stop(bus)

    async def test_summary(self, bus, tracker):
        await tracker.start(bus)
        await bus.publish("cost.recorded", {
            "tenant_id": "a", "model": "t", "total_cost": 1.0, "total_tokens": 100,
        })
        await bus.publish("cost.recorded", {
            "tenant_id": "b", "model": "t", "total_cost": 2.0, "total_tokens": 200,
        })

        summary = tracker.get_summary()
        assert summary["tenant_count"] == 2
        assert summary["total_cost"] == 3.0
        assert summary["total_tokens"] == 300
        assert summary["total_requests"] == 2
        await tracker.stop(bus)


class TestMeteringEndpoints:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_list_usage_empty(self, client):
        resp = await client.get("/api/v1/usage")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_usage_unknown(self, client):
        resp = await client.get("/api/v1/usage/unknown")
        assert resp.status_code == 200
        assert resp.json()["total_cost"] == 0.0

    async def test_list_after_events(self, client, app, tracker, bus):
        await tracker.start(bus)
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 0.05, "total_tokens": 500,
        })

        resp = await client.get("/api/v1/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["tenant_id"] == "acme"
        await tracker.stop(bus)

    async def test_get_tenant_usage(self, client, app, tracker, bus):
        await tracker.start(bus)
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "claude",
            "total_cost": 0.10, "total_tokens": 1000,
        })

        resp = await client.get("/api/v1/usage/acme")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == 0.1
        assert "hourly_cost" in data
        assert "daily_cost" in data
        await tracker.stop(bus)
