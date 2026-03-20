"""Agent executor — end-to-end flow from AgentSpec to streaming response.

This module ties together the plugin registry and framework adapters to
provide a single entry point for agent execution:

    spec → adapter lookup → create agent → execute → yield events

Supports event interceptors (RAPIDS governance layer) that can inspect,
modify, or halt events in the stream.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    EventInterceptor,
    FrameworkAdapter,
    StateSnapshot,
    ToolComponentSpec,
)
from ngen_framework_core.registry import AdapterRegistry, get_registry

logger = logging.getLogger(__name__)


class AgentExecutor:
    """Manages agent lifecycle: create, execute, checkpoint, restore, teardown.

    Uses the adapter registry to look up the correct framework adapter based
    on ``spec.framework``.

    Supports event interceptors (RAPIDS governance layer) that are applied
    to every event in the execution stream.
    """

    def __init__(
        self,
        registry: AdapterRegistry | None = None,
        interceptors: list[EventInterceptor] | None = None,
    ) -> None:
        self._registry = registry or get_registry()
        self._agents: dict[str, Any] = {}  # agent_name → framework-specific agent
        self._adapters: dict[str, FrameworkAdapter] = {}  # agent_name → adapter
        self._interceptors: list[EventInterceptor] = interceptors or []

    def add_interceptor(self, interceptor: EventInterceptor) -> None:
        """Add an event interceptor to the chain."""
        self._interceptors.append(interceptor)

    async def create(self, spec: AgentSpec) -> Any:
        """Create an agent from its spec using the appropriate adapter.

        Returns:
            The framework-specific agent object.

        Raises:
            KeyError: If no adapter is registered for ``spec.framework``.
        """
        adapter = self._registry.get(spec.framework)
        agent = await adapter.create_agent(spec)
        self._agents[spec.name] = agent
        self._adapters[spec.name] = adapter
        logger.info("Created agent '%s' with adapter '%s'", spec.name, adapter.name)
        return agent

    async def execute(
        self,
        agent_name: str,
        input_data: AgentInput,
    ) -> AsyncIterator[AgentEvent]:
        """Execute a previously created agent and yield streaming events.

        Events pass through the interceptor chain before being yielded.
        If any interceptor returns None, the event stream is halted.

        Raises:
            KeyError: If *agent_name* has not been created.
        """
        agent = self._get_agent(agent_name)
        adapter = self._adapters[agent_name]
        async for event in adapter.execute(agent, input_data):
            intercepted = await self._apply_interceptors(event)
            if intercepted is None:
                logger.info("Event stream halted by interceptor for agent '%s'", agent_name)
                return
            yield intercepted

    async def _apply_interceptors(self, event: AgentEvent) -> AgentEvent | None:
        """Pass an event through the interceptor chain."""
        current = event
        for interceptor in self._interceptors:
            result = await interceptor.intercept(current)
            if result is None:
                return None
            current = result
        return current

    async def checkpoint(self, agent_name: str) -> StateSnapshot:
        """Checkpoint a running agent's state.

        Raises:
            KeyError: If *agent_name* has not been created.
        """
        agent = self._get_agent(agent_name)
        adapter = self._adapters[agent_name]
        return await adapter.checkpoint(agent)

    async def restore(self, agent_name: str, snapshot: StateSnapshot) -> None:
        """Restore a previously created agent's state from a snapshot.

        Raises:
            KeyError: If *agent_name* has not been created.
        """
        agent = self._get_agent(agent_name)
        adapter = self._adapters[agent_name]
        await adapter.restore(agent, snapshot)

    async def teardown(self, agent_name: str) -> None:
        """Tear down and unregister an agent.

        Raises:
            KeyError: If *agent_name* has not been created.
        """
        agent = self._get_agent(agent_name)
        adapter = self._adapters[agent_name]
        await adapter.teardown(agent)
        del self._agents[agent_name]
        del self._adapters[agent_name]
        logger.info("Torn down agent '%s'", agent_name)

    async def teardown_all(self) -> None:
        """Tear down all managed agents."""
        for name in list(self._agents.keys()):
            await self.teardown(name)

    @property
    def agent_names(self) -> list[str]:
        """Return names of all managed agents."""
        return list(self._agents.keys())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_agent(self, name: str) -> Any:
        try:
            return self._agents[name]
        except KeyError:
            raise KeyError(
                f"Agent '{name}' not found. Created agents: {list(self._agents.keys())}"
            ) from None


# ---------------------------------------------------------------------------
# Tool executor (RAPIDS component type: Tool)
# ---------------------------------------------------------------------------


class ToolExecutor:
    """Executes deterministic tool components.

    Tools are stateless, no-LLM functions. The executor calls the handler
    and wraps the result in AgentEvent(RESPONSE).
    """

    def __init__(self, interceptors: list[EventInterceptor] | None = None) -> None:
        self._interceptors = interceptors or []

    async def execute(
        self,
        spec: ToolComponentSpec,
        input_data: dict[str, Any],
        handler_fn: Any | None = None,
    ) -> AgentEvent:
        """Execute a tool and return the result as an AgentEvent.

        Args:
            spec: The tool component specification.
            input_data: Input to pass to the handler.
            handler_fn: Callable to execute. If None, uses spec.handler
                        (must be resolved externally).

        Returns:
            AgentEvent with type RESPONSE containing the tool result.

        Raises:
            ValueError: If no handler is available.
        """
        if handler_fn is None:
            raise ValueError(
                f"No handler provided for tool '{spec.name}'. "
                "Pass handler_fn or resolve spec.handler externally."
            )

        try:
            if callable(handler_fn):
                import asyncio
                if asyncio.iscoroutinefunction(handler_fn):
                    result = await handler_fn(input_data)
                else:
                    result = handler_fn(input_data)
            else:
                raise TypeError(f"handler_fn must be callable, got {type(handler_fn)}")

            event = AgentEvent(
                type=AgentEventType.RESPONSE,
                data={"result": result, "tool": spec.name},
                agent_name=spec.name,
            )
        except Exception as e:
            event = AgentEvent(
                type=AgentEventType.ERROR,
                data={"error": str(e), "tool": spec.name},
                agent_name=spec.name,
            )

        # Apply interceptors
        for interceptor in self._interceptors:
            intercepted = await interceptor.intercept(event)
            if intercepted is None:
                return AgentEvent(
                    type=AgentEventType.ERROR,
                    data={"error": "Halted by interceptor", "tool": spec.name},
                    agent_name=spec.name,
                )
            event = intercepted

        return event
