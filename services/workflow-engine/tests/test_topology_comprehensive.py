"""Comprehensive topology test suite — covers all graph patterns, edge cases,
error handling, and stress scenarios.

Tests are organized by pattern complexity:
1. Core patterns (diamond, wide fan-out, deep chains)
2. Conditional routing (dynamic state-based branching)
3. Error handling (agent failures, partial completion)
4. Cycle detection
5. Edge cases (unreachable nodes, single-node graphs, empty conditions)
6. State isolation (parallel agents don't corrupt shared state)
7. Stress tests (many agents, deep nesting)
8. End-to-end API tests (YAML → execution → results)
"""

from __future__ import annotations

import asyncio
import time

import pytest

from ngen_framework_core.crd import WorkflowEdge
from ngen_framework_core.protocols import AgentEvent, AgentEventType, AgentInput

from workflow_engine.state import WorkflowState
from workflow_engine.topology import (
    GraphTopologyExecutor,
    TopologyError,
)


# ── Helpers ───────────────────────────────────────────────────────────────


def _edge(src: str, tgt: str, condition: str | None = None) -> WorkflowEdge:
    return WorkflowEdge(**{"from": src, "to": tgt, "condition": condition})


class OrderTrackingExecutor:
    """Records execution order, timing, and allows per-agent behavior."""

    def __init__(
        self,
        delay: float = 0.0,
        per_agent_delay: dict[str, float] | None = None,
        fail_agents: set[str] | None = None,
        output_fn=None,
    ):
        self.execution_order: list[str] = []
        self.start_times: dict[str, float] = {}
        self.end_times: dict[str, float] = {}
        self._delay = delay
        self._per_agent_delay = per_agent_delay or {}
        self._fail_agents = fail_agents or set()
        self._output_fn = output_fn  # (agent_name) -> str

    async def execute(self, agent_name: str, agent_input: AgentInput):
        self.start_times[agent_name] = time.monotonic()
        self.execution_order.append(agent_name)

        delay = self._per_agent_delay.get(agent_name, self._delay)
        if delay:
            await asyncio.sleep(delay)

        if agent_name in self._fail_agents:
            self.end_times[agent_name] = time.monotonic()
            yield AgentEvent(
                type=AgentEventType.ERROR,
                data={"error": f"Agent {agent_name} failed"},
                agent_name=agent_name,
                timestamp=time.time(),
            )
            return

        output_text = (
            self._output_fn(agent_name)
            if self._output_fn
            else f"Output from {agent_name}"
        )

        yield AgentEvent(
            type=AgentEventType.TEXT_DELTA,
            data={"text": output_text},
            agent_name=agent_name,
            timestamp=time.time(),
        )
        yield AgentEvent(
            type=AgentEventType.DONE,
            data={},
            agent_name=agent_name,
            timestamp=time.time(),
        )
        self.end_times[agent_name] = time.monotonic()


async def _run_graph(agents, edges, executor=None, state=None):
    """Helper to run a graph and collect events."""
    executor = executor or OrderTrackingExecutor()
    state = state or WorkflowState()
    graph = GraphTopologyExecutor()
    events = []
    async for event in graph.execute(
        agents=agents,
        edges=edges,
        executor=executor,
        state=state,
        input_data=AgentInput(messages=[{"role": "user", "content": "test"}]),
    ):
        events.append(event)
    return events, executor, state


# ═══════════════════════════════════════════════════════════════════════════
# 1. CORE GRAPH PATTERNS
# ═══════════════════════════════════════════════════════════════════════════


class TestDiamondDAG:
    """Classic diamond pattern: A→{B,C}→D."""

    @pytest.mark.asyncio
    async def test_diamond_execution_order(self):
        """D must execute after BOTH B and C complete."""
        events, executor, _ = await _run_graph(
            agents=["a", "b", "c", "d"],
            edges=[
                _edge("a", "b"), _edge("a", "c"),
                _edge("b", "d"), _edge("c", "d"),
            ],
        )
        order = executor.execution_order
        assert order[0] == "a"
        assert order[-1] == "d"
        assert set(order[1:3]) == {"b", "c"}

    @pytest.mark.asyncio
    async def test_diamond_d_waits_for_both_predecessors(self):
        """D should not start until both B and C are done."""
        executor = OrderTrackingExecutor(
            per_agent_delay={"b": 0.2, "c": 0.1}
        )
        events, executor, _ = await _run_graph(
            agents=["a", "b", "c", "d"],
            edges=[
                _edge("a", "b"), _edge("a", "c"),
                _edge("b", "d"), _edge("c", "d"),
            ],
            executor=executor,
        )
        # D should start after the slower of B,C finishes
        assert executor.start_times["d"] >= executor.end_times["b"]
        assert executor.start_times["d"] >= executor.end_times["c"]

    @pytest.mark.asyncio
    async def test_diamond_state_from_both_branches(self):
        """D should have access to both B and C outputs in state."""
        _, _, state = await _run_graph(
            agents=["a", "b", "c", "d"],
            edges=[
                _edge("a", "b"), _edge("a", "c"),
                _edge("b", "d"), _edge("c", "d"),
            ],
        )
        s = state.to_dict()
        assert "b_output" in s
        assert "c_output" in s


class TestWideFanOut:
    """Single node fans out to many parallel workers."""

    @pytest.mark.asyncio
    async def test_five_way_fan_out(self):
        workers = ["w1", "w2", "w3", "w4", "w5"]
        edges = [_edge("root", w) for w in workers]
        events, executor, _ = await _run_graph(
            agents=["root"] + workers, edges=edges,
        )
        assert executor.execution_order[0] == "root"
        assert set(executor.execution_order[1:]) == set(workers)

    @pytest.mark.asyncio
    async def test_ten_way_fan_out_fan_in(self):
        """Root → 10 workers → collector."""
        workers = [f"w{i}" for i in range(10)]
        edges = [_edge("root", w) for w in workers]
        edges += [_edge(w, "collector") for w in workers]
        events, executor, _ = await _run_graph(
            agents=["root"] + workers + ["collector"],
            edges=edges,
        )
        assert executor.execution_order[0] == "root"
        assert executor.execution_order[-1] == "collector"
        assert set(executor.execution_order[1:-1]) == set(workers)


class TestDeepChains:
    """Long sequential chains via graph edges."""

    @pytest.mark.asyncio
    async def test_twenty_node_chain(self):
        agents = [f"step-{i}" for i in range(20)]
        edges = [_edge(agents[i], agents[i + 1]) for i in range(19)]
        events, executor, _ = await _run_graph(agents=agents, edges=edges)
        assert executor.execution_order == agents

    @pytest.mark.asyncio
    async def test_fifty_node_chain(self):
        agents = [f"s{i}" for i in range(50)]
        edges = [_edge(agents[i], agents[i + 1]) for i in range(49)]
        events, executor, _ = await _run_graph(agents=agents, edges=edges)
        assert len(executor.execution_order) == 50
        assert executor.execution_order == agents


class TestMultiLevelFanIn:
    """Deeply nested fan-out/fan-in patterns."""

    @pytest.mark.asyncio
    async def test_two_level_fan_out_fan_in(self):
        """A→{B,C}, B→{D,E}, C→F, {D,E,F}→G."""
        events, executor, _ = await _run_graph(
            agents=["a", "b", "c", "d", "e", "f", "g"],
            edges=[
                _edge("a", "b"), _edge("a", "c"),
                _edge("b", "d"), _edge("b", "e"),
                _edge("c", "f"),
                _edge("d", "g"), _edge("e", "g"), _edge("f", "g"),
            ],
        )
        order = executor.execution_order
        assert order[0] == "a"
        assert order[-1] == "g"
        # G must be after D, E, and F
        g_idx = order.index("g")
        assert "d" in order[:g_idx]
        assert "e" in order[:g_idx]
        assert "f" in order[:g_idx]


# ═══════════════════════════════════════════════════════════════════════════
# 2. CONDITIONAL ROUTING
# ═══════════════════════════════════════════════════════════════════════════


class TestDynamicConditionalRouting:
    """Conditional edges that evaluate against runtime state."""

    @pytest.mark.asyncio
    async def test_branch_based_on_agent_output(self):
        """A outputs score, B runs if score > 50, C runs if score <= 50."""
        state = WorkflowState()
        # Pre-set state to simulate A's output
        await state.set("a_output", {"text": "score is 80"})
        await state.set("score", 80)

        events, executor, _ = await _run_graph(
            agents=["a", "b", "c"],
            edges=[
                _edge("a", "b", condition="score > 50"),
                _edge("a", "c", condition="score <= 50"),
            ],
            state=state,
        )
        # B should run (score=80 > 50), C should not
        assert "a" in executor.execution_order
        assert "b" in executor.execution_order
        assert "c" not in executor.execution_order

    @pytest.mark.asyncio
    async def test_all_conditions_false_stops(self):
        """If all outgoing conditions are false, no successors run."""
        state = WorkflowState()
        await state.set("x", 0)

        events, executor, _ = await _run_graph(
            agents=["a", "b", "c"],
            edges=[
                _edge("a", "b", condition="x > 100"),
                _edge("a", "c", condition="x > 200"),
            ],
            state=state,
        )
        assert executor.execution_order == ["a"]

    @pytest.mark.asyncio
    async def test_multiple_true_conditions_fan_out(self):
        """Multiple conditions true → multiple successors execute."""
        state = WorkflowState()
        await state.set("x", 50)

        events, executor, _ = await _run_graph(
            agents=["a", "b", "c"],
            edges=[
                _edge("a", "b", condition="x > 10"),
                _edge("a", "c", condition="x > 20"),
            ],
            state=state,
        )
        assert set(executor.execution_order) == {"a", "b", "c"}


# ═══════════════════════════════════════════════════════════════════════════
# 3. ERROR HANDLING
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentFailure:
    """What happens when an agent fails during execution."""

    @pytest.mark.asyncio
    async def test_failed_agent_emits_error_event(self):
        executor = OrderTrackingExecutor(fail_agents={"b"})
        events, _, _ = await _run_graph(
            agents=["a", "b"],
            edges=[_edge("a", "b")],
            executor=executor,
        )
        error_events = [e for e in events if e.type == AgentEventType.ERROR]
        assert len(error_events) >= 1

    @pytest.mark.asyncio
    async def test_no_edges_raises_topology_error(self):
        with pytest.raises(TopologyError, match="requires at least one edge"):
            await _run_graph(agents=["a", "b"], edges=[])


# ═══════════════════════════════════════════════════════════════════════════
# 4. CYCLE DETECTION
# ═══════════════════════════════════════════════════════════════════════════


class TestCycleDetection:
    """Graphs with cycles should not run forever."""

    @pytest.mark.asyncio
    async def test_self_loop_terminates(self):
        """A→A should not loop forever."""
        events, executor, _ = await _run_graph(
            agents=["a"],
            edges=[_edge("a", "a")],
        )
        # Should execute A once (visited set prevents re-execution)
        assert executor.execution_order.count("a") == 1

    @pytest.mark.asyncio
    async def test_two_node_cycle_terminates(self):
        """A→B→A should terminate via visited tracking."""
        events, executor, _ = await _run_graph(
            agents=["a", "b"],
            edges=[_edge("a", "b"), _edge("b", "a")],
        )
        # Each node executes once
        assert "a" in executor.execution_order
        assert "b" in executor.execution_order
        assert executor.execution_order.count("a") == 1
        assert executor.execution_order.count("b") == 1


# ═══════════════════════════════════════════════════════════════════════════
# 5. EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_unknown_agent_in_edge_skipped(self):
        """Edges referencing agents not in the agents list are ignored."""
        events, executor, _ = await _run_graph(
            agents=["a", "b"],
            edges=[_edge("a", "b"), _edge("b", "nonexistent")],
        )
        assert executor.execution_order == ["a", "b"]

    @pytest.mark.asyncio
    async def test_multiple_start_nodes(self):
        """Multiple nodes with no incoming edges all start."""
        events, executor, _ = await _run_graph(
            agents=["a", "b", "c"],
            edges=[_edge("a", "c"), _edge("b", "c")],
        )
        # A and B are both starts (no incoming), C is the sink
        assert executor.execution_order[-1] == "c"
        assert set(executor.execution_order[:2]) == {"a", "b"}

    @pytest.mark.asyncio
    async def test_condition_syntax_error_skips_edge(self):
        """Malformed condition should skip the edge, not crash."""
        events, executor, _ = await _run_graph(
            agents=["a", "b"],
            edges=[_edge("a", "b", condition="this is not valid python >>>")],
        )
        # B should not execute (condition evaluation fails → skips)
        assert executor.execution_order == ["a"]

    @pytest.mark.asyncio
    async def test_empty_condition_string_treated_as_unconditional(self):
        """Edge with empty condition should be treated as unconditional."""
        events, executor, _ = await _run_graph(
            agents=["a", "b"],
            edges=[_edge("a", "b", condition="")],
        )
        assert executor.execution_order == ["a", "b"]

    @pytest.mark.asyncio
    async def test_none_condition_treated_as_unconditional(self):
        events, executor, _ = await _run_graph(
            agents=["a", "b"],
            edges=[_edge("a", "b", condition=None)],
        )
        assert executor.execution_order == ["a", "b"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. STATE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════


class TestStateInGraph:
    @pytest.mark.asyncio
    async def test_each_agent_output_recorded(self):
        _, _, state = await _run_graph(
            agents=["a", "b", "c"],
            edges=[_edge("a", "b"), _edge("b", "c")],
        )
        s = state.to_dict()
        assert "a_output" in s
        assert "b_output" in s
        assert "c_output" in s

    @pytest.mark.asyncio
    async def test_parallel_agents_both_recorded(self):
        _, _, state = await _run_graph(
            agents=["root", "left", "right"],
            edges=[_edge("root", "left"), _edge("root", "right")],
        )
        s = state.to_dict()
        assert "left_output" in s
        assert "right_output" in s

    @pytest.mark.asyncio
    async def test_state_available_to_downstream(self):
        """Downstream agents should see upstream state in their input context."""
        received_contexts = {}

        class ContextCapturingExecutor:
            execution_order = []

            async def execute(self, agent_name, agent_input):
                self.execution_order.append(agent_name)
                received_contexts[agent_name] = dict(agent_input.context)
                yield AgentEvent(
                    type=AgentEventType.TEXT_DELTA,
                    data={"text": f"from {agent_name}"},
                    agent_name=agent_name,
                    timestamp=time.time(),
                )
                yield AgentEvent(
                    type=AgentEventType.DONE, data={},
                    agent_name=agent_name, timestamp=time.time(),
                )

        await _run_graph(
            agents=["a", "b"],
            edges=[_edge("a", "b")],
            executor=ContextCapturingExecutor(),
        )
        # B's context should contain A's output
        assert "a_output" in received_contexts["b"]


# ═══════════════════════════════════════════════════════════════════════════
# 7. STRESS TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestStress:
    @pytest.mark.asyncio
    async def test_100_agent_sequential_chain(self):
        """100 agents in a chain should complete."""
        n = 100
        agents = [f"a{i}" for i in range(n)]
        edges = [_edge(agents[i], agents[i + 1]) for i in range(n - 1)]
        events, executor, _ = await _run_graph(agents=agents, edges=edges)
        assert len(executor.execution_order) == n
        assert executor.execution_order == agents

    @pytest.mark.asyncio
    async def test_20_way_fan_out_fan_in(self):
        """Root → 20 workers → collector."""
        workers = [f"w{i}" for i in range(20)]
        edges = [_edge("root", w) for w in workers]
        edges += [_edge(w, "collector") for w in workers]
        events, executor, _ = await _run_graph(
            agents=["root"] + workers + ["collector"],
            edges=edges,
        )
        assert executor.execution_order[0] == "root"
        assert executor.execution_order[-1] == "collector"
        assert len(executor.execution_order) == 22  # root + 20 workers + collector


# ═══════════════════════════════════════════════════════════════════════════
# 8. COMPLEX REAL-WORLD PATTERNS
# ═══════════════════════════════════════════════════════════════════════════


class TestRealWorldPatterns:
    @pytest.mark.asyncio
    async def test_research_parallel_analysis_merge(self):
        """
        Real workflow: research → {sentiment, entities, topics} → merge → review
        """
        events, executor, _ = await _run_graph(
            agents=["researcher", "sentiment", "entities", "topics", "merger", "reviewer"],
            edges=[
                _edge("researcher", "sentiment"),
                _edge("researcher", "entities"),
                _edge("researcher", "topics"),
                _edge("sentiment", "merger"),
                _edge("entities", "merger"),
                _edge("topics", "merger"),
                _edge("merger", "reviewer"),
            ],
        )
        order = executor.execution_order
        assert order[0] == "researcher"
        assert order[-1] == "reviewer"
        assert order[-2] == "merger"
        # All three analysis agents ran between researcher and merger
        merger_idx = order.index("merger")
        assert "sentiment" in order[:merger_idx]
        assert "entities" in order[:merger_idx]
        assert "topics" in order[:merger_idx]

    @pytest.mark.asyncio
    async def test_document_processing_pipeline(self):
        """
        Doc pipeline: parser → {ocr, text_extract} → combiner → validator → output
        """
        events, executor, _ = await _run_graph(
            agents=["parser", "ocr", "text_extract", "combiner", "validator", "output"],
            edges=[
                _edge("parser", "ocr"),
                _edge("parser", "text_extract"),
                _edge("ocr", "combiner"),
                _edge("text_extract", "combiner"),
                _edge("combiner", "validator"),
                _edge("validator", "output"),
            ],
        )
        order = executor.execution_order
        assert order[0] == "parser"
        assert order[-1] == "output"
        assert order[-2] == "validator"
        assert order[-3] == "combiner"

    @pytest.mark.asyncio
    async def test_conditional_triage_workflow(self):
        """
        Triage: classifier → specialist-a (if category==A)
                           → specialist-b (if category==B)
        """
        state = WorkflowState()
        await state.set("category", "A")

        events, executor, _ = await _run_graph(
            agents=["classifier", "specialist-a", "specialist-b"],
            edges=[
                _edge("classifier", "specialist-a", condition="category == 'A'"),
                _edge("classifier", "specialist-b", condition="category == 'B'"),
            ],
            state=state,
        )
        assert "classifier" in executor.execution_order
        assert "specialist-a" in executor.execution_order
        assert "specialist-b" not in executor.execution_order
