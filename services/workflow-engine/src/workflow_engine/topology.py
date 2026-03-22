"""Topology executors for the four supported workflow patterns.

Each executor implements the same interface: given a list of agents, edges,
an AgentExecutor, shared WorkflowState, and input data, it runs the agents
according to the topology and yields AgentEvents.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from ngen_framework_core.crd import TopologyType, WorkflowEdge
from ngen_framework_core.executor import AgentExecutor
from ngen_framework_core.protocols import AgentEvent, AgentEventType, AgentInput

from workflow_engine.errors import TopologyError
from workflow_engine.resilience import (
    CircuitBreakerRegistry,
    ResilienceConfig,
    execute_with_resilience,
)
from workflow_engine.state import WorkflowState, safe_eval_condition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sequential
# ---------------------------------------------------------------------------


class SequentialTopologyExecutor:
    """Execute agents one after another in declaration order.

    Each agent receives the accumulated state from all previous agents.
    """

    async def execute(
        self,
        agents: list[str],
        edges: list[WorkflowEdge],
        executor: AgentExecutor,
        state: WorkflowState,
        input_data: AgentInput,
        resilience_configs: dict[str, ResilienceConfig] | None = None,
        circuit_registry: CircuitBreakerRegistry | None = None,
    ) -> AsyncIterator[AgentEvent]:
        for agent_name in agents:
            await state.set_current_agent(agent_name)
            # Build input with current state context
            agent_input = AgentInput(
                messages=input_data.messages,
                context={**input_data.context, **state.to_dict()},
                session_id=input_data.session_id,
            )

            resilience = (resilience_configs or {}).get(agent_name)
            if resilience and (resilience.retry.max_retries > 0 or resilience.timeout.timeout_seconds or resilience.circuit_breaker_enabled):
                # Use resilient execution
                events = await execute_with_resilience(
                    agent_name=agent_name,
                    execute_fn=lambda _name=agent_name, _input=agent_input: executor.execute(_name, _input),
                    resilience=resilience,
                    circuit_registry=circuit_registry,
                )
                collected_text: list[str] = []
                for event in events:
                    if event.type == AgentEventType.TEXT_DELTA:
                        collected_text.append(event.data.get("text", ""))
                    yield event
            else:
                collected_text = []
                async for event in executor.execute(agent_name, agent_input):
                    if event.type == AgentEventType.TEXT_DELTA:
                        collected_text.append(event.data.get("text", ""))
                    yield event

            # Record the agent's output into shared state
            output = {"text": "".join(collected_text)}
            await state.record_agent_output(agent_name, output)
            await state.set(f"{agent_name}_output", output)

        await state.set_current_agent(None)


# ---------------------------------------------------------------------------
# Parallel
# ---------------------------------------------------------------------------


class ParallelTopologyExecutor:
    """Execute all agents concurrently and merge outputs."""

    async def execute(
        self,
        agents: list[str],
        edges: list[WorkflowEdge],
        executor: AgentExecutor,
        state: WorkflowState,
        input_data: AgentInput,
        resilience_configs: dict[str, ResilienceConfig] | None = None,
        circuit_registry: CircuitBreakerRegistry | None = None,
    ) -> AsyncIterator[AgentEvent]:
        # Collect all events from all agents running in parallel
        agent_texts: dict[str, list[str]] = {name: [] for name in agents}

        async def _run_agent(name: str) -> list[AgentEvent]:
            agent_input = AgentInput(
                messages=input_data.messages,
                context={**input_data.context, **state.to_dict()},
                session_id=input_data.session_id,
            )
            resilience = (resilience_configs or {}).get(name)
            if resilience and (resilience.retry.max_retries > 0 or resilience.timeout.timeout_seconds or resilience.circuit_breaker_enabled):
                events = await execute_with_resilience(
                    agent_name=name,
                    execute_fn=lambda _name=name, _input=agent_input: executor.execute(_name, _input),
                    resilience=resilience,
                    circuit_registry=circuit_registry,
                )
            else:
                events = []
                async for event in executor.execute(name, agent_input):
                    events.append(event)

            for event in events:
                if event.type == AgentEventType.TEXT_DELTA:
                    agent_texts[name].append(event.data.get("text", ""))
            return events

        # Run all agents concurrently
        results = await asyncio.gather(
            *[_run_agent(name) for name in agents],
            return_exceptions=True,
        )

        # Yield all events and record outputs
        for i, (name, result) in enumerate(zip(agents, results)):
            if isinstance(result, Exception):
                yield AgentEvent(
                    type=AgentEventType.ERROR,
                    data={"error": str(result)},
                    agent_name=name,
                )
                continue

            for event in result:
                yield event

            output = {"text": "".join(agent_texts[name])}
            await state.record_agent_output(name, output)
            await state.set(f"{name}_output", output)


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


class GraphTopologyExecutor:
    """Execute agents following a directed acyclic graph with parallel support.

    Uses a data-flow execution model:
    - Tracks in-degree (unsatisfied predecessor count) per node
    - Nodes with in_degree == 0 are "ready" to execute
    - If multiple nodes are ready simultaneously, they run in parallel
    - Supports fan-in (wait for all predecessors) and fan-out (parallel branches)
    - Edge conditions are evaluated against workflow state

    This handles mixed patterns: sequential chains, parallel branches,
    conditional routing, and fan-in convergence in a single graph.
    """

    MAX_ITERATIONS = 100  # Guard against cycles

    async def execute(
        self,
        agents: list[str],
        edges: list[WorkflowEdge],
        executor: AgentExecutor,
        state: WorkflowState,
        input_data: AgentInput,
        resilience_configs: dict[str, ResilienceConfig] | None = None,
        circuit_registry: CircuitBreakerRegistry | None = None,
    ) -> AsyncIterator[AgentEvent]:
        if not edges:
            raise TopologyError("Graph topology requires at least one edge")

        # Build adjacency and reverse-adjacency lists
        adjacency: dict[str, list[WorkflowEdge]] = defaultdict(list)
        predecessors: dict[str, list[WorkflowEdge]] = defaultdict(list)
        targets: set[str] = set()
        sources: set[str] = set()
        for edge in edges:
            adjacency[edge.source].append(edge)
            predecessors[edge.target].append(edge)
            sources.add(edge.source)
            targets.add(edge.target)

        agent_set = set(agents)
        all_nodes = (sources | targets) & agent_set

        # Compute initial in-degree (number of incoming edges per node)
        in_degree: dict[str, int] = {n: 0 for n in all_nodes}
        for edge in edges:
            if edge.target in in_degree:
                in_degree[edge.target] += 1

        # Start nodes: in_degree == 0
        ready: list[str] = [n for n in agents if n in all_nodes and in_degree.get(n, 0) == 0]
        if not ready:
            ready = [agents[0]]

        completed: set[str] = set()
        iterations = 0

        while ready and iterations < self.MAX_ITERATIONS:
            iterations += 1

            if len(ready) == 1:
                # Single node ready — execute sequentially
                node = ready.pop(0)
                async for event in self._execute_agent(
                    node, executor, state, input_data,
                    resilience_configs, circuit_registry,
                ):
                    yield event
                completed.add(node)
            else:
                # Multiple nodes ready — execute in parallel
                logger.info("Executing %d agents in parallel: %s", len(ready), ready)
                parallel_nodes = list(ready)
                ready.clear()

                # Collect events from all parallel agents
                all_events: list[list[AgentEvent]] = await asyncio.gather(*[
                    self._execute_agent_collect(
                        node, executor, state, input_data,
                        resilience_configs, circuit_registry,
                    )
                    for node in parallel_nodes
                ])

                # Yield events from all parallel agents
                for node, events in zip(parallel_nodes, all_events):
                    for event in events:
                        yield event
                    completed.add(node)

            # After executing, find newly ready nodes
            ready.clear()
            for node in list(completed):
                for edge in adjacency.get(node, []):
                    target = edge.target
                    if target in completed or target not in agent_set:
                        continue

                    # Check edge condition
                    if edge.condition:
                        try:
                            if not safe_eval_condition(edge.condition, state.to_dict()):
                                logger.debug(
                                    "Edge %s→%s condition '%s' is False, skipping",
                                    edge.source, edge.target, edge.condition,
                                )
                                continue
                        except Exception:
                            logger.warning(
                                "Edge %s→%s condition '%s' failed, skipping",
                                edge.source, edge.target, edge.condition,
                            )
                            continue

                    # Check if ALL predecessors of target are completed
                    all_preds_done = all(
                        pred_edge.source in completed
                        for pred_edge in predecessors.get(target, [])
                    )
                    if all_preds_done and target not in ready:
                        ready.append(target)

        await state.set_current_agent(None)

    async def _execute_agent(
        self,
        agent_name: str,
        executor: AgentExecutor,
        state: WorkflowState,
        input_data: AgentInput,
        resilience_configs: dict[str, ResilienceConfig] | None,
        circuit_registry: CircuitBreakerRegistry | None,
    ) -> AsyncIterator[AgentEvent]:
        """Execute a single agent and yield its events."""
        await state.set_current_agent(agent_name)
        agent_input = AgentInput(
            messages=input_data.messages,
            context={**input_data.context, **state.to_dict()},
            session_id=input_data.session_id,
        )

        collected_text: list[str] = []
        resilience = (resilience_configs or {}).get(agent_name)
        if resilience and (resilience.retry.max_retries > 0 or resilience.timeout.timeout_seconds or resilience.circuit_breaker_enabled):
            events = await execute_with_resilience(
                agent_name=agent_name,
                execute_fn=lambda _name=agent_name, _input=agent_input: executor.execute(_name, _input),
                resilience=resilience,
                circuit_registry=circuit_registry,
            )
            for event in events:
                if event.type == AgentEventType.TEXT_DELTA:
                    collected_text.append(event.data.get("text", ""))
                yield event
        else:
            async for event in executor.execute(agent_name, agent_input):
                if event.type == AgentEventType.TEXT_DELTA:
                    collected_text.append(event.data.get("text", ""))
                yield event

        output = {"text": "".join(collected_text)}
        await state.record_agent_output(agent_name, output)
        await state.set(f"{agent_name}_output", output)

    async def _execute_agent_collect(
        self,
        agent_name: str,
        executor: AgentExecutor,
        state: WorkflowState,
        input_data: AgentInput,
        resilience_configs: dict[str, ResilienceConfig] | None,
        circuit_registry: CircuitBreakerRegistry | None,
    ) -> list[AgentEvent]:
        """Execute a single agent and collect all events (for parallel execution)."""
        events: list[AgentEvent] = []
        async for event in self._execute_agent(
            agent_name, executor, state, input_data,
            resilience_configs, circuit_registry,
        ):
            events.append(event)
        return events


# ---------------------------------------------------------------------------
# Hierarchical
# ---------------------------------------------------------------------------


class HierarchicalTopologyExecutor:
    """Execute agents in a supervisor-worker pattern.

    The first agent acts as the supervisor. Its output determines which
    sub-agents to invoke. Sub-agents run sequentially, and their outputs
    are aggregated back for the supervisor's final response.
    """

    async def execute(
        self,
        agents: list[str],
        edges: list[WorkflowEdge],
        executor: AgentExecutor,
        state: WorkflowState,
        input_data: AgentInput,
        resilience_configs: dict[str, ResilienceConfig] | None = None,
        circuit_registry: CircuitBreakerRegistry | None = None,
    ) -> AsyncIterator[AgentEvent]:
        if len(agents) < 2:
            raise TopologyError(
                "Hierarchical topology requires at least 2 agents "
                "(1 supervisor + 1 worker)"
            )

        supervisor = agents[0]
        workers = agents[1:]

        async def _exec_agent(name: str, inp: AgentInput) -> tuple[list[AgentEvent], list[str]]:
            """Execute a single agent with optional resilience."""
            resilience = (resilience_configs or {}).get(name)
            texts: list[str] = []
            if resilience and (resilience.retry.max_retries > 0 or resilience.timeout.timeout_seconds or resilience.circuit_breaker_enabled):
                events = await execute_with_resilience(
                    agent_name=name,
                    execute_fn=lambda _n=name, _i=inp: executor.execute(_n, _i),
                    resilience=resilience,
                    circuit_registry=circuit_registry,
                )
                for ev in events:
                    if ev.type == AgentEventType.TEXT_DELTA:
                        texts.append(ev.data.get("text", ""))
                return events, texts
            else:
                events = []
                async for ev in executor.execute(name, inp):
                    events.append(ev)
                    if ev.type == AgentEventType.TEXT_DELTA:
                        texts.append(ev.data.get("text", ""))
                return events, texts

        # Phase 1: Run supervisor to get delegation decisions
        await state.set_current_agent(supervisor)
        agent_input = AgentInput(
            messages=input_data.messages,
            context={**input_data.context, **state.to_dict()},
            session_id=input_data.session_id,
        )
        sup_events, supervisor_text = await _exec_agent(supervisor, agent_input)
        for event in sup_events:
            yield event

        supervisor_output = {"text": "".join(supervisor_text)}
        await state.record_agent_output(supervisor, supervisor_output)
        await state.set(f"{supervisor}_output", supervisor_output)

        # Phase 2: Run workers sequentially
        for worker in workers:
            await state.set_current_agent(worker)
            worker_input = AgentInput(
                messages=input_data.messages,
                context={
                    **input_data.context,
                    **state.to_dict(),
                    "supervisor_output": supervisor_output,
                },
                session_id=input_data.session_id,
            )
            wk_events, worker_text = await _exec_agent(worker, worker_input)
            for event in wk_events:
                yield event

            output = {"text": "".join(worker_text)}
            await state.record_agent_output(worker, output)
            await state.set(f"{worker}_output", output)

        await state.set_current_agent(None)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_TOPOLOGY_MAP = {
    TopologyType.SEQUENTIAL: SequentialTopologyExecutor,
    TopologyType.PARALLEL: ParallelTopologyExecutor,
    TopologyType.GRAPH: GraphTopologyExecutor,
    TopologyType.HIERARCHICAL: HierarchicalTopologyExecutor,
}


def get_topology_executor(
    topology: TopologyType,
) -> (
    SequentialTopologyExecutor
    | ParallelTopologyExecutor
    | GraphTopologyExecutor
    | HierarchicalTopologyExecutor
):
    """Return the appropriate topology executor for the given type.

    Raises:
        TopologyError: If the topology type is not supported.
    """
    cls = _TOPOLOGY_MAP.get(topology)
    if cls is None:
        raise TopologyError(f"Unsupported topology type: {topology}")
    return cls()
