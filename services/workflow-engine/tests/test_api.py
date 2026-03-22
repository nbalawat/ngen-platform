"""Tests for Workflow Engine REST API."""

from __future__ import annotations

import pytest

from ngen_framework_core.crd import TopologyType


class TestRunWorkflow:
    async def test_run_sequential(self, client, make_crd, crd_to_yaml):
        crd = make_crd(
            agents=["agent-a", "agent-b"],
            topology=TopologyType.SEQUENTIAL,
        )
        resp = await client.post(
            "/workflows/run",
            json={
                "workflow_yaml": crd_to_yaml(crd),
                "input_data": {"query": "hello"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert len(data["events"]) > 0

    async def test_run_parallel(self, client, make_crd, crd_to_yaml):
        crd = make_crd(
            agents=["agent-a", "agent-b"],
            topology=TopologyType.PARALLEL,
        )
        resp = await client.post(
            "/workflows/run",
            json={"workflow_yaml": crd_to_yaml(crd)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"

    async def test_invalid_yaml(self, client):
        resp = await client.post(
            "/workflows/run",
            json={"workflow_yaml": "not: valid: yaml: ["},
        )
        assert resp.status_code == 400

    async def test_wrong_kind(self, client):
        resp = await client.post(
            "/workflows/run",
            json={
                "workflow_yaml": "apiVersion: ngen.io/v1\nkind: Agent\nmetadata:\n  name: x\nspec:\n  framework: langgraph\n  model:\n    name: mock\n  systemPrompt: hello\n",
            },
        )
        assert resp.status_code == 400
        assert "Workflow" in resp.json()["detail"]


class TestListRuns:
    async def test_list_empty(self, client):
        resp = await client.get("/workflows/runs")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_after_run(self, client, make_crd, crd_to_yaml):
        crd = make_crd(agents=["agent-a", "agent-b"])
        await client.post(
            "/workflows/run",
            json={"workflow_yaml": crd_to_yaml(crd)},
        )
        resp = await client.get("/workflows/runs")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_filter_by_status(self, client, make_crd, crd_to_yaml):
        crd = make_crd(agents=["agent-a", "agent-b"])
        await client.post(
            "/workflows/run",
            json={"workflow_yaml": crd_to_yaml(crd)},
        )
        resp = await client.get("/workflows/runs?status=completed")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = await client.get("/workflows/runs?status=pending")
        assert resp.status_code == 200
        assert len(resp.json()) == 0


class TestGetRun:
    async def test_get_existing(self, client, make_crd, crd_to_yaml):
        crd = make_crd(agents=["agent-a", "agent-b"])
        run_resp = await client.post(
            "/workflows/run",
            json={"workflow_yaml": crd_to_yaml(crd)},
        )
        run_id = run_resp.json()["run_id"]

        resp = await client.get(f"/workflows/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["run_id"] == run_id

    async def test_get_not_found(self, client):
        resp = await client.get("/workflows/runs/nonexistent-id")
        assert resp.status_code == 404


class TestApproveRun:
    async def test_approve_not_found(self, client):
        resp = await client.post("/workflows/runs/nonexistent/approve")
        assert resp.status_code == 404

    async def test_approve_not_waiting(self, client, make_crd, crd_to_yaml):
        crd = make_crd(agents=["agent-a", "agent-b"])
        run_resp = await client.post(
            "/workflows/run",
            json={"workflow_yaml": crd_to_yaml(crd)},
        )
        run_id = run_resp.json()["run_id"]

        resp = await client.post(f"/workflows/runs/{run_id}/approve")
        assert resp.status_code == 409


class TestCancelRun:
    async def test_cancel_not_found(self, client):
        resp = await client.delete("/workflows/runs/nonexistent")
        assert resp.status_code == 404


class TestWorkflowValidation:
    """Workflow requests should be validated before execution."""

    async def test_rejects_empty_agents(self, client, crd_to_yaml, make_crd):
        """Workflow with 0 agents should be rejected."""
        import yaml as _yaml
        raw = {
            "apiVersion": "ngen.io/v1",
            "kind": "Workflow",
            "metadata": {"name": "empty-workflow"},
            "spec": {
                "agents": [],
                "topology": "sequential",
            },
        }
        resp = await client.post(
            "/workflows/run",
            json={"workflow_yaml": _yaml.dump(raw)},
        )
        assert resp.status_code == 400
        assert "agent" in resp.json()["detail"].lower()

    async def test_sequential_needs_at_least_two_agents(self, client, make_crd, crd_to_yaml):
        """Sequential workflow with 1 agent is a degenerate case."""
        crd = make_crd(
            agents=["only-one"],
            topology=TopologyType.SEQUENTIAL,
        )
        resp = await client.post(
            "/workflows/run",
            json={"workflow_yaml": crd_to_yaml(crd)},
        )
        assert resp.status_code == 400
        assert "sequential" in resp.json()["detail"].lower() or "agent" in resp.json()["detail"].lower()

    async def test_parallel_needs_at_least_two_agents(self, client, make_crd, crd_to_yaml):
        """Parallel workflow with 1 agent doesn't make sense."""
        crd = make_crd(
            agents=["only-one"],
            topology=TopologyType.PARALLEL,
        )
        resp = await client.post(
            "/workflows/run",
            json={"workflow_yaml": crd_to_yaml(crd)},
        )
        assert resp.status_code == 400

    async def test_graph_needs_edges(self, client, make_crd, crd_to_yaml):
        """Graph topology with multiple agents but no edges is invalid."""
        crd = make_crd(
            agents=["agent-a", "agent-b", "agent-c"],
            topology=TopologyType.GRAPH,
        )
        resp = await client.post(
            "/workflows/run",
            json={"workflow_yaml": crd_to_yaml(crd)},
        )
        assert resp.status_code == 400
        assert "edge" in resp.json()["detail"].lower()

    async def test_valid_sequential_passes(self, client, make_crd, crd_to_yaml):
        """Valid sequential workflow with 2+ agents should succeed."""
        crd = make_crd(
            agents=["agent-a", "agent-b"],
            topology=TopologyType.SEQUENTIAL,
        )
        resp = await client.post(
            "/workflows/run",
            json={"workflow_yaml": crd_to_yaml(crd)},
        )
        assert resp.status_code == 200

    async def test_valid_graph_with_edges_passes(self, client, make_crd, crd_to_yaml):
        """Valid graph workflow with agents and edges should succeed."""
        crd = make_crd(
            agents=["agent-a", "agent-b"],
            topology=TopologyType.GRAPH,
            edges=[{"from": "agent-a", "to": "agent-b"}],
        )
        resp = await client.post(
            "/workflows/run",
            json={"workflow_yaml": crd_to_yaml(crd)},
        )
        assert resp.status_code == 200

    async def test_cancel_completed(self, client, make_crd, crd_to_yaml):
        crd = make_crd(agents=["agent-a", "agent-b"])
        run_resp = await client.post(
            "/workflows/run",
            json={"workflow_yaml": crd_to_yaml(crd)},
        )
        run_id = run_resp.json()["run_id"]

        resp = await client.delete(f"/workflows/runs/{run_id}")
        assert resp.status_code == 409


class TestHealthEndpoint:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
