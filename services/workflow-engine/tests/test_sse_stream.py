"""Integration tests for SSE streaming endpoint."""

from __future__ import annotations

import asyncio
import json

import pytest

from ngen_framework_core.crd import TopologyType


def parse_sse_events(lines: list[str]) -> list[dict]:
    """Parse SSE lines into a list of {event, data} dicts."""
    events = []
    current_event = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith(":"):
            # SSE comment (keepalive)
            events.append({"event": "keepalive", "data": None})
        elif line.startswith("event: "):
            current_event = line[len("event: "):]
        elif line.startswith("data: "):
            data = json.loads(line[len("data: "):])
            events.append({"event": current_event or "message", "data": data})
            current_event = None
    return events


class TestStreamSequential:
    async def test_stream_returns_events(self, client, make_crd, crd_to_yaml):
        crd = make_crd(
            agents=["agent-a", "agent-b"],
            topology=TopologyType.SEQUENTIAL,
        )
        lines = []
        async with client.stream(
            "POST",
            "/workflows/run/stream",
            json={
                "workflow_yaml": crd_to_yaml(crd),
                "input_data": {"query": "hello"},
            },
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            async for line in resp.aiter_lines():
                lines.append(line)

        events = parse_sse_events(lines)
        assert len(events) > 0

        # Should have a terminal "done" event with run_id/status
        terminal = [
            e for e in events
            if e["event"] == "done" and e["data"] and "run_id" in e["data"]
        ]
        assert len(terminal) == 1
        assert terminal[0]["data"]["status"] == "completed"
        assert terminal[0]["data"]["run_id"]

    async def test_stream_contains_agent_events(self, client, make_crd, crd_to_yaml):
        crd = make_crd(
            agents=["agent-a", "agent-b"],
            topology=TopologyType.SEQUENTIAL,
        )
        lines = []
        async with client.stream(
            "POST",
            "/workflows/run/stream",
            json={"workflow_yaml": crd_to_yaml(crd)},
        ) as resp:
            async for line in resp.aiter_lines():
                lines.append(line)

        events = parse_sse_events(lines)
        event_types = {e["event"] for e in events}
        # InMemoryAdapter yields THINKING, TEXT_DELTA, DONE
        assert "thinking" in event_types or "text_delta" in event_types


class TestStreamParallel:
    async def test_stream_parallel_agents(self, client, make_crd, crd_to_yaml):
        crd = make_crd(
            agents=["agent-a", "agent-b"],
            topology=TopologyType.PARALLEL,
        )
        lines = []
        async with client.stream(
            "POST",
            "/workflows/run/stream",
            json={"workflow_yaml": crd_to_yaml(crd)},
        ) as resp:
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                lines.append(line)

        events = parse_sse_events(lines)
        terminal = [
            e for e in events
            if e["event"] == "done" and e["data"] and "run_id" in e["data"]
        ]
        assert len(terminal) == 1
        assert terminal[0]["data"]["status"] == "completed"

        # Should see events from both agents
        agent_names = {
            e["data"].get("agent_name")
            for e in events
            if e.get("data") and "agent_name" in e.get("data", {})
        }
        assert "agent-a" in agent_names
        assert "agent-b" in agent_names


class TestStreamInvalidInput:
    async def test_invalid_yaml_returns_400(self, client):
        resp = await client.post(
            "/workflows/run/stream",
            json={"workflow_yaml": "not: valid: yaml: ["},
        )
        assert resp.status_code == 400

    async def test_wrong_kind_returns_400(self, client):
        resp = await client.post(
            "/workflows/run/stream",
            json={
                "workflow_yaml": "apiVersion: ngen.io/v1\nkind: Agent\nmetadata:\n  name: x\nspec:\n  framework: langgraph\n  model:\n    name: mock\n  systemPrompt: hello\n",
            },
        )
        assert resp.status_code == 400


class TestStreamRunTracked:
    async def test_run_appears_in_list(self, client, make_crd, crd_to_yaml):
        crd = make_crd(agents=["agent-a", "agent-b"])
        lines = []
        async with client.stream(
            "POST",
            "/workflows/run/stream",
            json={"workflow_yaml": crd_to_yaml(crd)},
        ) as resp:
            async for line in resp.aiter_lines():
                lines.append(line)

        events = parse_sse_events(lines)
        done_event = next(
            e for e in events
            if e["event"] == "done" and e["data"] and "run_id" in e["data"]
        )
        run_id = done_event["data"]["run_id"]

        # Verify run is tracked via the REST API
        list_resp = await client.get("/workflows/runs")
        assert list_resp.status_code == 200
        runs = list_resp.json()
        run_ids = [r["run_id"] for r in runs]
        assert run_id in run_ids

        # Verify individual run lookup
        get_resp = await client.get(f"/workflows/runs/{run_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["run_id"] == run_id


class TestStreamHITLApproval:
    async def test_hitl_approval_via_engine(self, engine, make_crd):
        """Verify HITL approval flow at the engine level.

        httpx ASGI transport buffers entire SSE responses, making it
        impossible to test concurrent stream + approve via HTTP. Instead,
        we test the engine's async iterator directly with concurrent approval.
        """
        from ngen_framework_core.protocols import AgentEventType

        crd = make_crd(
            agents=["agent-a", "agent-b"],
            topology=TopologyType.SEQUENTIAL,
            hitl_gate="agent-a",
        )
        events: list = []
        run_id_holder: list[str] = []

        async def collect_events():
            async for event in engine.run_workflow(
                workflow=crd, input_data={"query": "test"}
            ):
                events.append(event)
                # Capture run_id from engine state
                if not run_id_holder:
                    runs = engine.list_runs()
                    if runs:
                        run_id_holder.append(runs[-1].run_id)

        async def approve_when_waiting():
            for _ in range(200):
                await asyncio.sleep(0.02)
                escalations = [
                    e for e in events
                    if e.type == AgentEventType.ESCALATION and "gate" in e.data
                ]
                if escalations and run_id_holder:
                    engine.approve_run(run_id_holder[0])
                    return

        await asyncio.gather(collect_events(), approve_when_waiting())

        # Should have an escalation event for the HITL gate
        escalations = [
            e for e in events
            if e.type == AgentEventType.ESCALATION and "gate" in e.data
        ]
        assert len(escalations) == 1
        assert escalations[0].data["gate"] == "agent-a"

        # Should complete after approval — both agents should have run
        done_events = [e for e in events if e.type == AgentEventType.DONE]
        agent_names = {e.agent_name for e in done_events}
        assert "agent-a" in agent_names
        assert "agent-b" in agent_names

        # Run should be completed
        run = engine.get_run(run_id_holder[0])
        assert run.status.value == "completed"
