"""Tests for enhanced graph executor with parallel support."""

from __future__ import annotations

import asyncio
import time

import pytest

from ngen_framework_core.crd import WorkflowEdge
from ngen_framework_core.protocols import AgentEventType, AgentInput

from workflow_engine.state import WorkflowState
from workflow_engine.topology import GraphTopologyExecutor


class MockExecutor:
    """Records execution order and timing for test assertions."""

    def __init__(self, delay: float = 0.0):
        self.execution_order: list[str] = []
        self.execution_times: dict[str, float] = {}
        self._delay = delay

    async def execute(self, agent_name: str, agent_input: AgentInput):
        start = time.monotonic()
        self.execution_order.append(agent_name)
        if self._delay:
            await asyncio.sleep(self._delay)
        self.execution_times[agent_name] = time.monotonic() - start

        from ngen_framework_core.protocols import AgentEvent
        yield AgentEvent(
            type=AgentEventType.TEXT_DELTA,
            data={"text": f"Output from {agent_name}"},
            agent_name=agent_name,
            timestamp=time.time(),
        )
        yield AgentEvent(
            type=AgentEventType.DONE,
            data={},
            agent_name=agent_name,
            timestamp=time.time(),
        )


def _edge(src: str, tgt: str, condition: str | None = None) -> WorkflowEdge:
    return WorkflowEdge(**{"from": src, "to": tgt, "condition": condition})


class TestSequentialChain:
    @pytest.mark.asyncio
    async def test_a_b_c_executes_in_order(self):
        """A→B→C should execute sequentially."""
        executor = MockExecutor()
        state = WorkflowState()
        graph = GraphTopologyExecutor()

        events = []
        async for event in graph.execute(
            agents=["a", "b", "c"],
            edges=[_edge("a", "b"), _edge("b", "c")],
            executor=executor,
            state=state,
            input_data=AgentInput(messages=[{"role": "user", "content": "test"}]),
        ):
            events.append(event)

        assert executor.execution_order == ["a", "b", "c"]


class TestParallelBranches:
    @pytest.mark.asyncio
    async def test_fan_out(self):
        """A→{B,C} — B and C should both execute after A."""
        executor = MockExecutor(delay=0.1)
        state = WorkflowState()
        graph = GraphTopologyExecutor()

        events = []
        async for event in graph.execute(
            agents=["a", "b", "c"],
            edges=[_edge("a", "b"), _edge("a", "c")],
            executor=executor,
            state=state,
            input_data=AgentInput(messages=[{"role": "user", "content": "test"}]),
        ):
            events.append(event)

        # A executes first
        assert executor.execution_order[0] == "a"
        # B and C both execute (order may vary since they're parallel)
        assert set(executor.execution_order[1:]) == {"b", "c"}

    @pytest.mark.asyncio
    async def test_fan_in_waits(self):
        """A→{B,C}→D — D should only run after BOTH B and C complete."""
        executor = MockExecutor()
        state = WorkflowState()
        graph = GraphTopologyExecutor()

        events = []
        async for event in graph.execute(
            agents=["a", "b", "c", "d"],
            edges=[
                _edge("a", "b"), _edge("a", "c"),
                _edge("b", "d"), _edge("c", "d"),
            ],
            executor=executor,
            state=state,
            input_data=AgentInput(messages=[{"role": "user", "content": "test"}]),
        ):
            events.append(event)

        # A first, then B and C (parallel), then D
        assert executor.execution_order[0] == "a"
        assert executor.execution_order[-1] == "d"
        # B and C must both appear before D
        d_idx = executor.execution_order.index("d")
        assert "b" in executor.execution_order[:d_idx]
        assert "c" in executor.execution_order[:d_idx]


class TestConditionalEdges:
    @pytest.mark.asyncio
    async def test_condition_true(self):
        """Edge with true condition allows traversal."""
        executor = MockExecutor()
        state = WorkflowState()
        graph = GraphTopologyExecutor()

        events = []
        async for event in graph.execute(
            agents=["a", "b"],
            edges=[_edge("a", "b", condition="True")],
            executor=executor,
            state=state,
            input_data=AgentInput(messages=[{"role": "user", "content": "test"}]),
        ):
            events.append(event)

        assert executor.execution_order == ["a", "b"]

    @pytest.mark.asyncio
    async def test_condition_false_skips(self):
        """Edge with false condition skips the target."""
        executor = MockExecutor()
        state = WorkflowState()
        graph = GraphTopologyExecutor()

        events = []
        async for event in graph.execute(
            agents=["a", "b"],
            edges=[_edge("a", "b", condition="False")],
            executor=executor,
            state=state,
            input_data=AgentInput(messages=[{"role": "user", "content": "test"}]),
        ):
            events.append(event)

        assert executor.execution_order == ["a"]


class TestMixedWorkflow:
    @pytest.mark.asyncio
    async def test_sequential_then_parallel_then_converge(self):
        """A→B→{C,D}→E — mixed sequential + parallel + fan-in."""
        executor = MockExecutor()
        state = WorkflowState()
        graph = GraphTopologyExecutor()

        events = []
        async for event in graph.execute(
            agents=["a", "b", "c", "d", "e"],
            edges=[
                _edge("a", "b"),
                _edge("b", "c"), _edge("b", "d"),
                _edge("c", "e"), _edge("d", "e"),
            ],
            executor=executor,
            state=state,
            input_data=AgentInput(messages=[{"role": "user", "content": "test"}]),
        ):
            events.append(event)

        # A and B sequential, then C and D parallel, then E
        assert executor.execution_order[0] == "a"
        assert executor.execution_order[1] == "b"
        assert executor.execution_order[-1] == "e"
        # C and D must both appear before E
        e_idx = executor.execution_order.index("e")
        assert "c" in executor.execution_order[:e_idx]
        assert "d" in executor.execution_order[:e_idx]
