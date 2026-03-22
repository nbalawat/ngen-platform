"""Integration tests for memory event publishing during agent invocation.

Verifies that memory.written events are published to the event bus
when agents are invoked. Uses InMemoryEventBus. No mocks.
"""

from __future__ import annotations

import pytest


class TestMemoryEventPublishing:
    async def test_invoke_publishes_memory_written_events(self, client, app):
        """Agent invocation should publish memory.written events."""
        await client.post("/agents", json={
            "name": "event-agent", "framework": "in-memory",
        })

        await client.post("/agents/event-agent/invoke", json={
            "messages": [{"role": "user", "content": "Hello event test"}],
        })

        # Check the event bus for memory.written events
        bus = app.state.event_bus
        memory_events = bus.events_for("memory.written")
        # At least 2: user message + assistant response
        assert len(memory_events) >= 2

        # Verify event data structure
        for evt in memory_events:
            assert "tenant_id" in evt.data
            assert "agent_name" in evt.data
            assert evt.data["agent_name"] == "event-agent"
            assert "memory_type" in evt.data
            assert "size_bytes" in evt.data
            assert "token_estimate" in evt.data

    async def test_clear_memory_publishes_deleted_event(self, client, app):
        """Clearing agent memory should publish memory.deleted event."""
        await client.post("/agents", json={
            "name": "clear-event-agent", "framework": "in-memory",
        })
        await client.post("/agents/clear-event-agent/invoke", json={
            "messages": [{"role": "user", "content": "data to clear"}],
        })

        bus = app.state.event_bus
        bus.clear()  # Clear history before delete

        await client.delete("/agents/clear-event-agent/memory")

        deleted_events = bus.events_for("memory.deleted")
        assert len(deleted_events) >= 1
        assert deleted_events[0].data["agent_name"] == "clear-event-agent"
        assert deleted_events[0].data["entry_count"] >= 1

    async def test_memory_events_contain_tenant_context(self, client, app):
        """Events should reflect tenant headers when provided."""
        await client.post("/agents", json={
            "name": "tenant-event-agent", "framework": "in-memory",
        })

        bus = app.state.event_bus
        bus.clear()

        await client.post(
            "/agents/tenant-event-agent/invoke",
            json={"messages": [{"role": "user", "content": "Tenant context test"}]},
            headers={"x-org-id": "acme-corp"},
        )

        memory_events = bus.events_for("memory.written")
        assert len(memory_events) >= 1
        assert memory_events[0].data["tenant_id"] == "acme-corp"
