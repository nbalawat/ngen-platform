"""Tests for MCP manager lifecycle event publishing.

Verifies that server CRUD operations publish lifecycle events to the event bus.
Uses InMemoryEventBus — no mocks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

import mcp_manager.routes as routes
from mcp_manager.app import create_app
from ngen_common.events import InMemoryEventBus, Subjects


@pytest.fixture()
def bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture()
def mcp_app(bus):
    routes._repository = None
    app = create_app()
    app.state.event_bus = bus
    return app


@pytest.fixture()
async def client(mcp_app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=mcp_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://mcp-manager"
    ) as c:
        yield c


@pytest.fixture()
def server_payload():
    return {
        "name": "test-server",
        "namespace": "test-ns",
        "endpoint": "http://test:3000/mcp",
        "transport": "streamable-http",
        "tools": [
            {
                "name": "search",
                "description": "Search docs",
                "parameters": [
                    {"name": "query", "type": "string", "required": True},
                ],
            },
        ],
    }


class TestServerRegisteredEvent:
    async def test_register_publishes_event(self, client, bus, server_payload):
        resp = await client.post("/api/v1/servers", json=server_payload)
        assert resp.status_code == 201

        events = bus.events_for("lifecycle.server_registered")
        assert len(events) == 1
        data = events[0].data
        assert data["name"] == "test-server"
        assert data["namespace"] == "test-ns"
        assert data["transport"] == "streamable-http"
        assert data["tool_count"] == 1

    async def test_register_event_source(self, client, bus, server_payload):
        await client.post("/api/v1/servers", json=server_payload)
        events = bus.events_for("lifecycle.server_registered")
        assert events[0].source == "mcp-manager"

    async def test_register_failure_no_event(self, client, bus, server_payload):
        await client.post("/api/v1/servers", json=server_payload)
        resp = await client.post("/api/v1/servers", json=server_payload)
        assert resp.status_code == 409
        # Only one event from first registration
        events = bus.events_for("lifecycle.server_registered")
        assert len(events) == 1

    async def test_multiple_servers_each_publish(self, client, bus):
        for name in ("srv-a", "srv-b", "srv-c"):
            resp = await client.post("/api/v1/servers", json={
                "name": name,
                "namespace": "default",
                "endpoint": "http://test:3000/mcp",
                "transport": "streamable-http",
                "tools": [],
            })
            assert resp.status_code == 201

        events = bus.events_for("lifecycle.server_registered")
        assert len(events) == 3
        names = {e.data["name"] for e in events}
        assert names == {"srv-a", "srv-b", "srv-c"}


class TestServerDeletedEvent:
    async def test_delete_publishes_event(self, client, bus, server_payload):
        resp = await client.post("/api/v1/servers", json=server_payload)
        server_id = resp.json()["id"]

        resp = await client.delete(f"/api/v1/servers/{server_id}")
        assert resp.status_code == 204

        events = bus.events_for("lifecycle.server_deleted")
        assert len(events) == 1
        data = events[0].data
        assert data["server_id"] == server_id
        assert data["name"] == "test-server"
        assert data["namespace"] == "test-ns"

    async def test_delete_nonexistent_no_event(self, client, bus):
        resp = await client.delete("/api/v1/servers/nonexistent-id")
        assert resp.status_code == 404
        events = bus.events_for("lifecycle.server_deleted")
        assert len(events) == 0

    async def test_delete_event_source(self, client, bus, server_payload):
        resp = await client.post("/api/v1/servers", json=server_payload)
        server_id = resp.json()["id"]
        await client.delete(f"/api/v1/servers/{server_id}")
        events = bus.events_for("lifecycle.server_deleted")
        assert events[0].source == "mcp-manager"


class TestLifecycleFlow:
    async def test_register_then_delete(self, client, bus):
        resp = await client.post("/api/v1/servers", json={
            "name": "lifecycle-srv",
            "namespace": "default",
            "endpoint": "http://test:3000/mcp",
            "transport": "streamable-http",
            "tools": [],
        })
        assert resp.status_code == 201
        server_id = resp.json()["id"]

        resp = await client.delete(f"/api/v1/servers/{server_id}")
        assert resp.status_code == 204

        registered = bus.events_for("lifecycle.server_registered")
        deleted = bus.events_for("lifecycle.server_deleted")
        assert len(registered) == 1
        assert len(deleted) == 1
        assert registered[0].data["name"] == "lifecycle-srv"
        assert deleted[0].data["name"] == "lifecycle-srv"
