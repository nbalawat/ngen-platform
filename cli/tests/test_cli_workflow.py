"""Tests for CLI workflow commands against real in-process services."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import yaml
from click.testing import CliRunner

from ngen_cli.main import cli


def _make_workflow_yaml(
    name: str = "test-workflow",
    agents: list[str] | None = None,
    topology: str = "sequential",
) -> str:
    """Create a valid WorkflowCRD YAML string."""
    agents = agents or ["agent-a", "agent-b"]
    return yaml.dump({
        "apiVersion": "ngen.io/v1",
        "kind": "Workflow",
        "metadata": {"name": name},
        "spec": {
            "agents": [{"ref": a} for a in agents],
            "topology": topology,
        },
    })


class TestWorkflowRun:
    async def test_run_blocking(self, workflow_client):
        """Run a workflow via the API directly (blocking mode)."""
        workflow_yaml = _make_workflow_yaml()
        resp = await workflow_client.post(
            "/workflows/run",
            json={"workflow_yaml": workflow_yaml, "input_data": {"query": "test"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert len(data["events"]) > 0

    async def test_run_stream(self, workflow_client):
        """Run a workflow via SSE streaming."""
        workflow_yaml = _make_workflow_yaml()
        lines = []
        async with workflow_client.stream(
            "POST",
            "/workflows/run/stream",
            json={"workflow_yaml": workflow_yaml},
        ) as resp:
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                lines.append(line)

        # Should have events including a terminal done
        assert any("done" in line for line in lines)

    async def test_list_runs_after_execution(self, workflow_client):
        """After running a workflow, it should appear in the list."""
        workflow_yaml = _make_workflow_yaml(agents=["agent-a"])
        await workflow_client.post(
            "/workflows/run",
            json={"workflow_yaml": workflow_yaml},
        )
        resp = await workflow_client.get("/workflows/runs")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) >= 1
        assert runs[0]["status"] == "completed"

    async def test_get_run(self, workflow_client):
        """Get a specific run by ID."""
        workflow_yaml = _make_workflow_yaml(agents=["agent-a"])
        run_resp = await workflow_client.post(
            "/workflows/run",
            json={"workflow_yaml": workflow_yaml},
        )
        run_id = run_resp.json()["run_id"]

        resp = await workflow_client.get(f"/workflows/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["run_id"] == run_id

    async def test_get_run_not_found(self, workflow_client):
        """Get a non-existent run returns 404."""
        resp = await workflow_client.get("/workflows/runs/nonexistent")
        assert resp.status_code == 404


class TestWorkflowCLIValidation:
    def test_invalid_yaml_file(self):
        """CLI rejects invalid YAML files."""
        runner = CliRunner()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("not: valid: yaml: [")
            f.flush()
            result = runner.invoke(cli, ["workflow", "run", f.name, "--no-stream"])
        assert result.exit_code != 0

    def test_wrong_kind(self):
        """CLI rejects non-Workflow CRDs."""
        runner = CliRunner()
        wrong_yaml = yaml.dump({
            "apiVersion": "ngen.io/v1",
            "kind": "Agent",
            "metadata": {"name": "x"},
            "spec": {},
        })
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(wrong_yaml)
            f.flush()
            result = runner.invoke(cli, ["workflow", "run", f.name, "--no-stream"])
        assert result.exit_code != 0
        assert "Workflow" in result.output


class TestWorkflowParallel:
    async def test_parallel_topology(self, workflow_client):
        """Run parallel topology and verify both agents execute."""
        workflow_yaml = _make_workflow_yaml(
            agents=["agent-a", "agent-b"],
            topology="parallel",
        )
        resp = await workflow_client.post(
            "/workflows/run",
            json={"workflow_yaml": workflow_yaml},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        # Should have events from both agents
        agent_names = {e.get("agent_name") for e in data["events"]}
        assert "agent-a" in agent_names
        assert "agent-b" in agent_names
