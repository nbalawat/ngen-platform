"""Tests for topology executors."""

from __future__ import annotations

import pytest

from ngen_framework_core.crd import TopologyType, WorkflowEdge
from ngen_framework_core.executor import AgentExecutor
from ngen_framework_core.protocols import AgentEventType, AgentInput, AgentSpec, ModelRef

from workflow_engine.errors import TopologyError
from workflow_engine.state import WorkflowState
from workflow_engine.topology import (
    GraphTopologyExecutor,
    HierarchicalTopologyExecutor,
    ParallelTopologyExecutor,
    SequentialTopologyExecutor,
    get_topology_executor,
)


async def _create_agents(executor: AgentExecutor, names: list[str]) -> None:
    """Helper to create test agents."""
    for name in names:
        spec = AgentSpec(
            name=name,
            description=f"Test agent {name}",
            framework="in-memory",
            model=ModelRef(name="mock-model"),
            system_prompt="test",
        )
        await executor.create(spec)


def _make_input() -> AgentInput:
    return AgentInput(
        messages=[{"role": "user", "content": "test"}],
        context={},
    )


class TestSequentialTopology:
    async def test_runs_agents_in_order(self, executor):
        agents = ["agent-a", "agent-b", "agent-c"]
        await _create_agents(executor, agents)

        topo = SequentialTopologyExecutor()
        state = WorkflowState()
        events = []

        async for event in topo.execute(
            agents, [], executor, state, _make_input()
        ):
            events.append(event)

        # Each agent produces 3 events (THINKING, TEXT_DELTA, DONE)
        assert len(events) == 9

        # Check events are in order: agent-a, then agent-b, then agent-c
        done_agents = [e.agent_name for e in events if e.type == AgentEventType.DONE]
        assert done_agents == ["agent-a", "agent-b", "agent-c"]

    async def test_state_accumulates(self, executor):
        agents = ["agent-a", "agent-b"]
        await _create_agents(executor, agents)

        topo = SequentialTopologyExecutor()
        state = WorkflowState({"initial": True})

        async for _ in topo.execute(agents, [], executor, state, _make_input()):
            pass

        # Both agents should have recorded output
        assert "agent-a_output" in state.to_dict()
        assert "agent-b_output" in state.to_dict()
        assert state.get("initial") is True


class TestParallelTopology:
    async def test_runs_all_agents(self, executor):
        agents = ["agent-a", "agent-b"]
        await _create_agents(executor, agents)

        topo = ParallelTopologyExecutor()
        state = WorkflowState()
        events = []

        async for event in topo.execute(
            agents, [], executor, state, _make_input()
        ):
            events.append(event)

        # Both agents produce events
        assert len(events) == 6
        done_agents = {e.agent_name for e in events if e.type == AgentEventType.DONE}
        assert done_agents == {"agent-a", "agent-b"}

    async def test_outputs_merged(self, executor):
        agents = ["agent-a", "agent-b"]
        await _create_agents(executor, agents)

        topo = ParallelTopologyExecutor()
        state = WorkflowState()

        async for _ in topo.execute(agents, [], executor, state, _make_input()):
            pass

        assert "agent-a_output" in state.to_dict()
        assert "agent-b_output" in state.to_dict()


class TestGraphTopology:
    async def test_follows_edges(self, executor):
        agents = ["agent-a", "agent-b", "agent-c"]
        await _create_agents(executor, agents)

        edges = [
            WorkflowEdge.model_validate({"from": "agent-a", "to": "agent-b"}),
            WorkflowEdge.model_validate({"from": "agent-b", "to": "agent-c"}),
        ]

        topo = GraphTopologyExecutor()
        state = WorkflowState()
        events = []

        async for event in topo.execute(
            agents, edges, executor, state, _make_input()
        ):
            events.append(event)

        # All three agents should run
        done_agents = [e.agent_name for e in events if e.type == AgentEventType.DONE]
        assert done_agents == ["agent-a", "agent-b", "agent-c"]

    async def test_condition_true(self, executor):
        agents = ["agent-a", "agent-b"]
        await _create_agents(executor, agents)

        edges = [
            WorkflowEdge.model_validate({
                "from": "agent-a",
                "to": "agent-b",
                "condition": "True",
            }),
        ]

        topo = GraphTopologyExecutor()
        state = WorkflowState()
        events = []

        async for event in topo.execute(
            agents, edges, executor, state, _make_input()
        ):
            events.append(event)

        done_agents = [e.agent_name for e in events if e.type == AgentEventType.DONE]
        assert done_agents == ["agent-a", "agent-b"]

    async def test_condition_false_skips_agent(self, executor):
        agents = ["agent-a", "agent-b"]
        await _create_agents(executor, agents)

        edges = [
            WorkflowEdge.model_validate({
                "from": "agent-a",
                "to": "agent-b",
                "condition": "False",
            }),
        ]

        topo = GraphTopologyExecutor()
        state = WorkflowState()
        events = []

        async for event in topo.execute(
            agents, edges, executor, state, _make_input()
        ):
            events.append(event)

        # Only agent-a should run, agent-b skipped due to False condition
        done_agents = [e.agent_name for e in events if e.type == AgentEventType.DONE]
        assert done_agents == ["agent-a"]

    async def test_no_edges_raises(self, executor):
        agents = ["agent-a"]
        await _create_agents(executor, agents)

        topo = GraphTopologyExecutor()
        state = WorkflowState()

        with pytest.raises(TopologyError, match="requires at least one edge"):
            async for _ in topo.execute(
                agents, [], executor, state, _make_input()
            ):
                pass


class TestHierarchicalTopology:
    async def test_supervisor_then_workers(self, executor):
        agents = ["supervisor", "worker-a", "worker-b"]
        await _create_agents(executor, agents)

        topo = HierarchicalTopologyExecutor()
        state = WorkflowState()
        events = []

        async for event in topo.execute(
            agents, [], executor, state, _make_input()
        ):
            events.append(event)

        done_agents = [e.agent_name for e in events if e.type == AgentEventType.DONE]
        assert done_agents == ["supervisor", "worker-a", "worker-b"]

    async def test_requires_at_least_two_agents(self, executor):
        agents = ["solo"]
        await _create_agents(executor, agents)

        topo = HierarchicalTopologyExecutor()
        state = WorkflowState()

        with pytest.raises(TopologyError, match="at least 2 agents"):
            async for _ in topo.execute(
                agents, [], executor, state, _make_input()
            ):
                pass

    async def test_supervisor_output_in_worker_context(self, executor):
        agents = ["supervisor", "worker"]
        await _create_agents(executor, agents)

        topo = HierarchicalTopologyExecutor()
        state = WorkflowState()

        async for _ in topo.execute(
            agents, [], executor, state, _make_input()
        ):
            pass

        assert "supervisor_output" in state.to_dict()
        assert "worker_output" in state.to_dict()


class TestTopologyFactory:
    def test_sequential(self):
        assert isinstance(
            get_topology_executor(TopologyType.SEQUENTIAL),
            SequentialTopologyExecutor,
        )

    def test_parallel(self):
        assert isinstance(
            get_topology_executor(TopologyType.PARALLEL),
            ParallelTopologyExecutor,
        )

    def test_graph(self):
        assert isinstance(
            get_topology_executor(TopologyType.GRAPH),
            GraphTopologyExecutor,
        )

    def test_hierarchical(self):
        assert isinstance(
            get_topology_executor(TopologyType.HIERARCHICAL),
            HierarchicalTopologyExecutor,
        )
