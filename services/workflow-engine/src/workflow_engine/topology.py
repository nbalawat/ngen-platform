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
    ) -> AsyncIterator[AgentEvent]:
        for agent_name in agents:
            await state.set_current_agent(agent_name)
            # Build input with current state context
            agent_input = AgentInput(
                messages=input_data.messages,
                context={**input_data.context, **state.to_dict()},
                session_id=input_data.session_id,
            )
            collected_text: list[str] = []
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
    ) -> AsyncIterator[AgentEvent]:
        # Collect all events from all agents running in parallel
        all_events: list[AgentEvent] = []
        agent_texts: dict[str, list[str]] = {name: [] for name in agents}

        async def _run_agent(name: str) -> list[AgentEvent]:
            events: list[AgentEvent] = []
            agent_input = AgentInput(
                messages=input_data.messages,
                context={**input_data.context, **state.to_dict()},
                session_id=input_data.session_id,
            )
            async for event in executor.execute(name, agent_input):
                events.append(event)
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
    """Execute agents following directed edges with conditional transitions.

    Builds an adjacency list from edges, starts at nodes with no incoming
    edges, and traverses via BFS. Edge conditions are evaluated against
    the current workflow state using safe_eval_condition.
    """

    MAX_ITERATIONS = 100  # Guard against cycles

    async def execute(
        self,
        agents: list[str],
        edges: list[WorkflowEdge],
        executor: AgentExecutor,
        state: WorkflowState,
        input_data: AgentInput,
    ) -> AsyncIterator[AgentEvent]:
        if not edges:
            raise TopologyError("Graph topology requires at least one edge")

        # Build adjacency list
        adjacency: dict[str, list[WorkflowEdge]] = defaultdict(list)
        targets: set[str] = set()
        sources: set[str] = set()
        for edge in edges:
            adjacency[edge.source].append(edge)
            sources.add(edge.source)
            targets.add(edge.target)

        # Find start nodes (nodes with no incoming edges)
        all_nodes = sources | targets
        start_nodes = [n for n in agents if n in (sources - targets)]
        if not start_nodes:
            # Fallback: use the first agent
            start_nodes = [agents[0]]

        # BFS traversal
        queue: list[str] = list(start_nodes)
        visited: set[str] = set()
        iterations = 0

        while queue and iterations < self.MAX_ITERATIONS:
            iterations += 1
            current = queue.pop(0)

            if current in visited:
                continue
            visited.add(current)

            if current not in [a for a in agents]:
                continue

            # Execute the current agent
            await state.set_current_agent(current)
            agent_input = AgentInput(
                messages=input_data.messages,
                context={**input_data.context, **state.to_dict()},
                session_id=input_data.session_id,
            )
            collected_text: list[str] = []
            async for event in executor.execute(current, agent_input):
                if event.type == AgentEventType.TEXT_DELTA:
                    collected_text.append(event.data.get("text", ""))
                yield event

            output = {"text": "".join(collected_text)}
            await state.record_agent_output(current, output)
            await state.set(f"{current}_output", output)

            # Evaluate outgoing edges and enqueue targets
            for edge in adjacency.get(current, []):
                if edge.condition:
                    try:
                        if not safe_eval_condition(edge.condition, state.to_dict()):
                            logger.debug(
                                "Edge %s→%s condition '%s' is False, skipping",
                                edge.source,
                                edge.target,
                                edge.condition,
                            )
                            continue
                    except Exception:
                        logger.warning(
                            "Edge %s→%s condition '%s' failed, skipping",
                            edge.source,
                            edge.target,
                            edge.condition,
                        )
                        continue

                if edge.target not in visited:
                    queue.append(edge.target)

        await state.set_current_agent(None)


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
    ) -> AsyncIterator[AgentEvent]:
        if len(agents) < 2:
            raise TopologyError(
                "Hierarchical topology requires at least 2 agents "
                "(1 supervisor + 1 worker)"
            )

        supervisor = agents[0]
        workers = agents[1:]

        # Phase 1: Run supervisor to get delegation decisions
        await state.set_current_agent(supervisor)
        agent_input = AgentInput(
            messages=input_data.messages,
            context={**input_data.context, **state.to_dict()},
            session_id=input_data.session_id,
        )
        supervisor_text: list[str] = []
        async for event in executor.execute(supervisor, agent_input):
            if event.type == AgentEventType.TEXT_DELTA:
                supervisor_text.append(event.data.get("text", ""))
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
            worker_text: list[str] = []
            async for event in executor.execute(worker, worker_input):
                if event.type == AgentEventType.TEXT_DELTA:
                    worker_text.append(event.data.get("text", ""))
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
