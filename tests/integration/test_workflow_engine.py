"""Integration tests: workflow engine — workflow run, execution, and SSE streaming.

Tests the workflow run lifecycle against the real containerized service.
The workflow engine accepts workflow definitions as YAML strings (WorkflowCRD format)
and does not have separate CRUD endpoints for workflow definitions.
"""

from __future__ import annotations

import uuid
import textwrap

import httpx
import pytest


def _make_workflow_yaml(name: str, topology: str = "sequential", agents: list[str] | None = None) -> str:
    """Build a valid WorkflowCRD YAML string."""
    if agents is None:
        agents = ["mock-agent"]
    agent_lines = "\n".join(f"  - ref: {a}" for a in agents)
    return (
        f"apiVersion: ngen.io/v1\n"
        f"kind: Workflow\n"
        f"metadata:\n"
        f"  name: {name}\n"
        f"  namespace: integration-test\n"
        f"spec:\n"
        f"  topology: {topology}\n"
        f"  agents:\n"
        f"{agent_lines}\n"
    )


# ---------------------------------------------------------------------------
# Workflow Run
# ---------------------------------------------------------------------------


class TestWorkflowRun:
    """Submit workflow runs and verify responses."""

    async def test_run_workflow(self, http: httpx.AsyncClient, engine_url):
        """Submit a workflow run and get results."""
        name = f"run-wf-{uuid.uuid4().hex[:8]}"
        resp = await http.post(
            f"{engine_url}/workflows/run",
            json={
                "workflow_yaml": _make_workflow_yaml(name),
                "input_data": {"message": "Hello from integration test"},
            },
        )
        assert resp.status_code == 200, f"Run failed: {resp.text}"
        data = resp.json()
        assert "run_id" in data
        assert data["status"] in ("completed", "running", "failed", "pending")

    async def test_run_workflow_with_input(self, http: httpx.AsyncClient, engine_url):
        """Workflow run should accept and process input data."""
        name = f"input-wf-{uuid.uuid4().hex[:8]}"
        resp = await http.post(
            f"{engine_url}/workflows/run",
            json={
                "workflow_yaml": _make_workflow_yaml(name),
                "input_data": {"question": "What is 2+2?"},
                "session_id": f"session-{uuid.uuid4().hex[:8]}",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert "events" in data

    async def test_run_parallel_topology(self, http: httpx.AsyncClient, engine_url):
        """Workflow with parallel topology should execute agents concurrently."""
        name = f"parallel-wf-{uuid.uuid4().hex[:8]}"
        resp = await http.post(
            f"{engine_url}/workflows/run",
            json={
                "workflow_yaml": _make_workflow_yaml(name, topology="parallel", agents=["agent-a", "agent-b"]),
                "input_data": {"message": "Parallel execution test"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("completed", "failed", "running")

    async def test_run_invalid_yaml(self, http: httpx.AsyncClient, engine_url):
        """Invalid YAML should return 400."""
        resp = await http.post(
            f"{engine_url}/workflows/run",
            json={
                "workflow_yaml": "this is not valid: yaml: [",
                "input_data": {},
            },
        )
        assert resp.status_code in (400, 422)

    async def test_run_wrong_kind(self, http: httpx.AsyncClient, engine_url):
        """YAML with wrong kind should return 400."""
        yaml_str = textwrap.dedent("""\
            apiVersion: ngen.io/v1
            kind: Agent
            metadata:
              name: wrong-kind
            spec:
              framework: default
              model:
                provider: mock
                name: mock-model
              systemPrompt: "test"
        """)
        resp = await http.post(
            f"{engine_url}/workflows/run",
            json={"workflow_yaml": yaml_str, "input_data": {}},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Run Management
# ---------------------------------------------------------------------------


class TestWorkflowRunManagement:
    """List and retrieve workflow runs."""

    async def test_list_runs(self, http: httpx.AsyncClient, engine_url):
        """List workflow runs."""
        resp = await http.get(f"{engine_url}/workflows/runs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_run_then_get(self, http: httpx.AsyncClient, engine_url):
        """Run a workflow then retrieve the run by ID."""
        name = f"get-run-{uuid.uuid4().hex[:8]}"
        run_resp = await http.post(
            f"{engine_url}/workflows/run",
            json={
                "workflow_yaml": _make_workflow_yaml(name),
                "input_data": {"message": "test"},
            },
        )
        assert run_resp.status_code == 200
        run_id = run_resp.json()["run_id"]

        get_resp = await http.get(f"{engine_url}/workflows/runs/{run_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["run_id"] == run_id

    async def test_get_nonexistent_run(self, http: httpx.AsyncClient, engine_url):
        resp = await http.get(f"{engine_url}/workflows/runs/nonexistent-run-xyz")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# SSE Streaming
# ---------------------------------------------------------------------------


class TestWorkflowSSEStreaming:
    """Test SSE streaming of workflow events."""

    async def test_stream_workflow(self, http: httpx.AsyncClient, engine_url):
        """Stream workflow execution via SSE and collect events."""
        name = f"stream-wf-{uuid.uuid4().hex[:8]}"

        events = []
        async with http.stream(
            "POST",
            f"{engine_url}/workflows/run/stream",
            json={
                "workflow_yaml": _make_workflow_yaml(name),
                "input_data": {"message": "Stream test"},
            },
            headers={"Accept": "text/event-stream"},
        ) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    events.append(line[5:].strip())
                if len(events) > 20:
                    break  # safety limit

        assert len(events) > 0, "No SSE events received"

    async def test_stream_contains_done_event(self, http: httpx.AsyncClient, engine_url):
        """SSE stream should end with a 'done' event."""
        name = f"done-wf-{uuid.uuid4().hex[:8]}"

        event_types = []
        async with http.stream(
            "POST",
            f"{engine_url}/workflows/run/stream",
            json={
                "workflow_yaml": _make_workflow_yaml(name),
                "input_data": {"message": "Done event test"},
            },
            headers={"Accept": "text/event-stream"},
        ) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_types.append(line[6:].strip())
                if len(event_types) > 30:
                    break

        assert "done" in event_types, f"No 'done' event found. Events: {event_types}"


# ---------------------------------------------------------------------------
# Agent Lifecycle Manager
# ---------------------------------------------------------------------------


class TestAgentLifecycleManager:
    """Test standalone agent CRUD and invocation via the workflow engine."""

    async def test_create_agent(self, http: httpx.AsyncClient, engine_url):
        name = f"integ-agent-{uuid.uuid4().hex[:8]}"
        resp = await http.post(
            f"{engine_url}/agents",
            json={
                "name": name,
                "description": "Integration test agent",
                "framework": "default",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == name
        assert data["status"] == "running"

    async def test_list_agents(self, http: httpx.AsyncClient, engine_url):
        resp = await http.get(f"{engine_url}/agents")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_agent(self, http: httpx.AsyncClient, engine_url):
        name = f"get-agent-{uuid.uuid4().hex[:8]}"
        await http.post(f"{engine_url}/agents", json={
            "name": name, "framework": "default",
        })
        resp = await http.get(f"{engine_url}/agents/{name}")
        assert resp.status_code == 200
        assert resp.json()["name"] == name

    async def test_get_nonexistent(self, http: httpx.AsyncClient, engine_url):
        resp = await http.get(f"{engine_url}/agents/nonexistent-xyz")
        assert resp.status_code == 404

    async def test_invoke_agent(self, http: httpx.AsyncClient, engine_url):
        name = f"invoke-agent-{uuid.uuid4().hex[:8]}"
        await http.post(f"{engine_url}/agents", json={
            "name": name, "framework": "default",
        })
        resp = await http.post(
            f"{engine_url}/agents/{name}/invoke",
            json={
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == name
        assert len(data["events"]) > 0

    async def test_delete_agent(self, http: httpx.AsyncClient, engine_url):
        name = f"del-agent-{uuid.uuid4().hex[:8]}"
        await http.post(f"{engine_url}/agents", json={
            "name": name, "framework": "default",
        })
        resp = await http.delete(f"{engine_url}/agents/{name}")
        assert resp.status_code == 204

        # Verify gone
        resp = await http.get(f"{engine_url}/agents/{name}")
        assert resp.status_code == 404

    async def test_duplicate_rejected(self, http: httpx.AsyncClient, engine_url):
        name = f"dup-agent-{uuid.uuid4().hex[:8]}"
        await http.post(f"{engine_url}/agents", json={
            "name": name, "framework": "default",
        })
        resp = await http.post(f"{engine_url}/agents", json={
            "name": name, "framework": "default",
        })
        assert resp.status_code == 409
