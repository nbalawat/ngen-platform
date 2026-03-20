"""Tests for WorkflowEngine."""

from __future__ import annotations

import pytest

from ngen_framework_core.crd import TopologyType
from ngen_framework_core.protocols import AgentEventType

from workflow_engine.engine import WorkflowEngine
from workflow_engine.errors import WorkflowNotFoundError
from workflow_engine.models import WorkflowRunStatus


class TestSequentialWorkflow:
    async def test_end_to_end(self, engine, make_crd):
        crd = make_crd(
            agents=["agent-a", "agent-b"],
            topology=TopologyType.SEQUENTIAL,
        )
        events = []
        async for event in engine.run_workflow(crd, {"query": "hello"}):
            events.append(event)

        done_agents = [e.agent_name for e in events if e.type == AgentEventType.DONE]
        assert done_agents == ["agent-a", "agent-b"]

    async def test_run_tracked(self, engine, make_crd):
        crd = make_crd(agents=["agent-a"])
        async for _ in engine.run_workflow(crd):
            pass

        runs = engine.list_runs()
        assert len(runs) == 1
        assert runs[0].status == WorkflowRunStatus.COMPLETED


class TestParallelWorkflow:
    async def test_end_to_end(self, engine, make_crd):
        crd = make_crd(
            agents=["agent-a", "agent-b"],
            topology=TopologyType.PARALLEL,
        )
        events = []
        async for event in engine.run_workflow(crd, {"query": "hello"}):
            events.append(event)

        done_agents = {e.agent_name for e in events if e.type == AgentEventType.DONE}
        assert done_agents == {"agent-a", "agent-b"}


class TestGraphWorkflow:
    async def test_with_edges(self, engine, make_crd):
        crd = make_crd(
            agents=["agent-a", "agent-b", "agent-c"],
            topology=TopologyType.GRAPH,
            edges=[
                {"from": "agent-a", "to": "agent-b"},
                {"from": "agent-b", "to": "agent-c"},
            ],
        )
        events = []
        async for event in engine.run_workflow(crd):
            events.append(event)

        done_agents = [e.agent_name for e in events if e.type == AgentEventType.DONE]
        assert done_agents == ["agent-a", "agent-b", "agent-c"]

    async def test_conditional_edge(self, engine, make_crd):
        crd = make_crd(
            agents=["agent-a", "agent-b"],
            topology=TopologyType.GRAPH,
            edges=[
                {"from": "agent-a", "to": "agent-b", "condition": "False"},
            ],
        )
        events = []
        async for event in engine.run_workflow(crd):
            events.append(event)

        done_agents = [e.agent_name for e in events if e.type == AgentEventType.DONE]
        assert done_agents == ["agent-a"]


class TestRunManagement:
    async def test_get_run(self, engine, make_crd):
        crd = make_crd(agents=["agent-a"])
        async for _ in engine.run_workflow(crd):
            pass

        runs = engine.list_runs()
        run = engine.get_run(runs[0].run_id)
        assert run.status == WorkflowRunStatus.COMPLETED

    async def test_get_run_not_found(self, engine):
        with pytest.raises(WorkflowNotFoundError):
            engine.get_run("nonexistent-id")

    async def test_list_runs_filter(self, engine, make_crd):
        crd = make_crd(agents=["agent-a"])
        async for _ in engine.run_workflow(crd):
            pass

        completed = engine.list_runs(status=WorkflowRunStatus.COMPLETED)
        assert len(completed) == 1
        pending = engine.list_runs(status=WorkflowRunStatus.PENDING)
        assert len(pending) == 0

    async def test_cancel_completed(self, engine, make_crd):
        crd = make_crd(agents=["agent-a"])
        async for _ in engine.run_workflow(crd):
            pass

        runs = engine.list_runs()
        assert engine.cancel_run(runs[0].run_id) is False

    async def test_cancel_nonexistent(self, engine):
        assert engine.cancel_run("nonexistent") is False

    async def test_multiple_runs(self, engine, make_crd):
        for i in range(3):
            crd = make_crd(
                name=f"workflow-{i}", agents=[f"agent-{i}"]
            )
            async for _ in engine.run_workflow(crd):
                pass

        assert len(engine.list_runs()) == 3
