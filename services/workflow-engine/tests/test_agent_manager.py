"""Tests for Agent Lifecycle Manager — CRUD and invocation of standalone agents.

Uses real InMemoryAdapter and InMemoryEventBus. No mocks.
"""

from __future__ import annotations

import pytest

from ngen_common.events import InMemoryEventBus


class TestAgentCreate:
    async def test_create_agent(self, client):
        resp = await client.post("/agents", json={
            "name": "test-agent",
            "description": "A test agent",
            "framework": "in-memory",
            "model": "default",
            "system_prompt": "You are helpful.",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-agent"
        assert data["description"] == "A test agent"
        assert data["framework"] == "in-memory"
        assert data["status"] == "running"
        assert data["created_at"] > 0

    async def test_create_duplicate_rejected(self, client):
        await client.post("/agents", json={
            "name": "dup-agent", "framework": "in-memory",
        })
        resp = await client.post("/agents", json={
            "name": "dup-agent", "framework": "in-memory",
        })
        assert resp.status_code == 409

    async def test_create_publishes_lifecycle_event(self, client, app):
        bus: InMemoryEventBus = app.state.event_bus
        await client.post("/agents", json={
            "name": "event-agent", "framework": "in-memory",
        })

        events = bus.events_for("lifecycle.agent_created")
        assert len(events) == 1
        assert events[0].data["name"] == "event-agent"
        assert events[0].source == "workflow-engine"


class TestAgentList:
    async def test_list_empty(self, client):
        resp = await client.get("/agents")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_agents(self, client):
        await client.post("/agents", json={
            "name": "agent-a", "framework": "in-memory",
        })
        await client.post("/agents", json={
            "name": "agent-b", "framework": "in-memory",
        })

        resp = await client.get("/agents")
        assert resp.status_code == 200
        names = {a["name"] for a in resp.json()}
        assert names == {"agent-a", "agent-b"}


class TestAgentGet:
    async def test_get_agent(self, client):
        await client.post("/agents", json={
            "name": "get-agent", "framework": "in-memory",
            "description": "Test agent",
        })

        resp = await client.get("/agents/get-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "get-agent"
        assert data["description"] == "Test agent"
        assert data["invocation_count"] == 0

    async def test_get_nonexistent(self, client):
        resp = await client.get("/agents/nonexistent")
        assert resp.status_code == 404


class TestAgentInvoke:
    async def test_invoke_agent(self, client):
        await client.post("/agents", json={
            "name": "invoke-agent", "framework": "in-memory",
        })

        resp = await client.post("/agents/invoke-agent/invoke", json={
            "messages": [{"role": "user", "content": "Hello"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "invoke-agent"
        assert len(data["events"]) > 0
        assert data["output"] is not None
        # Rich adapter produces context-aware output referencing the user's message
        assert len(data["output"]) > 10  # meaningful output, not just echo

    async def test_invoke_increments_count(self, client):
        await client.post("/agents", json={
            "name": "count-agent", "framework": "in-memory",
        })

        await client.post("/agents/count-agent/invoke", json={
            "messages": [{"role": "user", "content": "test"}],
        })
        await client.post("/agents/count-agent/invoke", json={
            "messages": [{"role": "user", "content": "test"}],
        })

        resp = await client.get("/agents/count-agent")
        assert resp.json()["invocation_count"] == 2

    async def test_invoke_nonexistent(self, client):
        resp = await client.post("/agents/nonexistent/invoke", json={
            "messages": [{"role": "user", "content": "test"}],
        })
        assert resp.status_code == 404

    async def test_invoke_returns_events(self, client):
        await client.post("/agents", json={
            "name": "events-agent", "framework": "in-memory",
        })

        resp = await client.post("/agents/events-agent/invoke", json={
            "messages": [{"role": "user", "content": "Hello"}],
        })
        events = resp.json()["events"]
        event_types = [e["type"] for e in events]
        assert "thinking" in event_types
        assert "text_delta" in event_types
        assert "done" in event_types


class TestAgentDelete:
    async def test_delete_agent(self, client):
        await client.post("/agents", json={
            "name": "delete-agent", "framework": "in-memory",
        })

        resp = await client.delete("/agents/delete-agent")
        assert resp.status_code == 204

        # Verify gone
        resp = await client.get("/agents/delete-agent")
        assert resp.status_code == 404

    async def test_delete_nonexistent(self, client):
        resp = await client.delete("/agents/nonexistent")
        assert resp.status_code == 404

    async def test_delete_publishes_lifecycle_event(self, client, app):
        bus: InMemoryEventBus = app.state.event_bus
        await client.post("/agents", json={
            "name": "del-event-agent", "framework": "in-memory",
        })
        await client.delete("/agents/del-event-agent")

        events = bus.events_for("lifecycle.agent_deleted")
        assert len(events) == 1
        assert events[0].data["name"] == "del-event-agent"


class TestFullAgentLifecycle:
    async def test_create_invoke_delete(self, client, app):
        bus: InMemoryEventBus = app.state.event_bus

        # Create
        resp = await client.post("/agents", json={
            "name": "lifecycle-agent",
            "framework": "in-memory",
            "description": "Full lifecycle test",
        })
        assert resp.status_code == 201

        # Invoke
        resp = await client.post("/agents/lifecycle-agent/invoke", json={
            "messages": [{"role": "user", "content": "Hello"}],
        })
        assert resp.status_code == 200
        assert resp.json()["output"] is not None

        # Check invocation count
        resp = await client.get("/agents/lifecycle-agent")
        assert resp.json()["invocation_count"] == 1

        # Delete
        resp = await client.delete("/agents/lifecycle-agent")
        assert resp.status_code == 204

        # Verify lifecycle events
        created = bus.events_for("lifecycle.agent_created")
        deleted = bus.events_for("lifecycle.agent_deleted")
        assert len(created) == 1
        assert len(deleted) == 1


class TestAgentSearch:
    """Agent list endpoint should support search/filter."""

    async def test_search_by_name(self, client):
        for name in ["customer-bot", "sales-bot", "ops-monitor"]:
            await client.post("/agents", json={
                "name": name, "framework": "in-memory",
                "description": f"Agent for {name.split('-')[0]}",
            })

        resp = await client.get("/agents?search=customer")
        assert resp.status_code == 200
        agents = resp.json()
        assert len(agents) == 1
        assert agents[0]["name"] == "customer-bot"

    async def test_search_by_description(self, client):
        await client.post("/agents", json={
            "name": "helper-a", "framework": "in-memory",
            "description": "Handles billing inquiries",
        })
        await client.post("/agents", json={
            "name": "helper-b", "framework": "in-memory",
            "description": "Handles technical support",
        })

        resp = await client.get("/agents?search=billing")
        agents = resp.json()
        assert len(agents) == 1
        assert agents[0]["name"] == "helper-a"

    async def test_search_case_insensitive(self, client):
        await client.post("/agents", json={
            "name": "DataAgent", "framework": "in-memory",
        })

        resp = await client.get("/agents?search=dataagent")
        agents = resp.json()
        assert len(agents) == 1

    async def test_search_no_results(self, client):
        await client.post("/agents", json={
            "name": "some-agent", "framework": "in-memory",
        })

        resp = await client.get("/agents?search=nonexistent")
        assert resp.json() == []

    async def test_search_empty_returns_all(self, client):
        await client.post("/agents", json={
            "name": "agent-x", "framework": "in-memory",
        })
        await client.post("/agents", json={
            "name": "agent-y", "framework": "in-memory",
        })

        resp = await client.get("/agents?search=")
        agents = resp.json()
        assert len(agents) >= 2
