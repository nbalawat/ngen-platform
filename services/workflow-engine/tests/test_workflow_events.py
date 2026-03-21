"""Tests for workflow lifecycle event publishing via NATS.

Uses InMemoryEventBus and real InMemoryAdapter. No mocks.
"""

from __future__ import annotations

import pytest

from ngen_framework_core.crd import TopologyType
from ngen_common.events import InMemoryEventBus, Subjects


class TestWorkflowStartedEvent:
    async def test_run_publishes_started(self, client, app, make_crd, crd_to_yaml):
        bus: InMemoryEventBus = app.state.event_bus
        crd = make_crd(agents=["agent-a"])

        resp = await client.post("/workflows/run", json={
            "workflow_yaml": crd_to_yaml(crd),
            "input_data": {"query": "test"},
        })
        assert resp.status_code == 200

        events = bus.events_for("audit.workflow_started")
        assert len(events) >= 1
        data = events[0].data
        assert data["workflow_name"] == "test-workflow"
        assert data["agent_count"] == 1

    async def test_stream_publishes_started(self, client, app, make_crd, crd_to_yaml):
        bus: InMemoryEventBus = app.state.event_bus
        crd = make_crd(agents=["agent-a", "agent-b"])

        lines = []
        async with client.stream(
            "POST", "/workflows/run/stream",
            json={"workflow_yaml": crd_to_yaml(crd)},
        ) as resp:
            async for line in resp.aiter_lines():
                lines.append(line)

        events = bus.events_for("audit.workflow_started")
        assert len(events) >= 1
        data = events[0].data
        assert data["streaming"] is True
        assert data["agent_count"] == 2

    async def test_started_event_source(self, client, app, make_crd, crd_to_yaml):
        bus: InMemoryEventBus = app.state.event_bus
        crd = make_crd(agents=["agent-a"])

        await client.post("/workflows/run", json={
            "workflow_yaml": crd_to_yaml(crd),
        })

        events = bus.events_for("audit.workflow_started")
        assert events[0].source == "workflow-engine"


class TestWorkflowCompletedEvent:
    async def test_run_publishes_completed(self, client, app, make_crd, crd_to_yaml):
        bus: InMemoryEventBus = app.state.event_bus
        crd = make_crd(agents=["agent-a"])

        resp = await client.post("/workflows/run", json={
            "workflow_yaml": crd_to_yaml(crd),
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

        events = bus.events_for("audit.workflow_completed")
        assert len(events) == 1
        data = events[0].data
        assert data["workflow_name"] == "test-workflow"
        assert "run_id" in data

    async def test_stream_publishes_completed(self, client, app, make_crd, crd_to_yaml):
        bus: InMemoryEventBus = app.state.event_bus
        crd = make_crd(agents=["agent-a"])

        lines = []
        async with client.stream(
            "POST", "/workflows/run/stream",
            json={"workflow_yaml": crd_to_yaml(crd)},
        ) as resp:
            async for line in resp.aiter_lines():
                lines.append(line)

        events = bus.events_for("audit.workflow_completed")
        assert len(events) == 1

    async def test_parallel_publishes_completed(self, client, app, make_crd, crd_to_yaml):
        bus: InMemoryEventBus = app.state.event_bus
        crd = make_crd(
            agents=["agent-a", "agent-b"],
            topology=TopologyType.PARALLEL,
        )

        resp = await client.post("/workflows/run", json={
            "workflow_yaml": crd_to_yaml(crd),
        })
        assert resp.status_code == 200

        events = bus.events_for("audit.workflow_completed")
        assert len(events) == 1


class TestWorkflowFailedEvent:
    async def test_invalid_yaml_no_started_event(self, client, app):
        bus: InMemoryEventBus = app.state.event_bus

        resp = await client.post("/workflows/run", json={
            "workflow_yaml": "not: valid: yaml: [",
        })
        assert resp.status_code == 400

        # Invalid YAML fails before workflow starts — no events
        started = bus.events_for("audit.workflow_started")
        assert len(started) == 0


class TestEventTopology:
    async def test_topology_in_started_event(self, client, app, make_crd, crd_to_yaml):
        bus: InMemoryEventBus = app.state.event_bus
        crd = make_crd(
            agents=["agent-a", "agent-b"],
            topology=TopologyType.PARALLEL,
        )

        await client.post("/workflows/run", json={
            "workflow_yaml": crd_to_yaml(crd),
        })

        events = bus.events_for("audit.workflow_started")
        assert events[0].data["topology"] == "parallel"
