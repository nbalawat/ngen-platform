"""Default framework adapter — built-in agent that echoes input.

This adapter provides a basic agent implementation that doesn't require
any external framework (LangGraph, CrewAI, etc.). It produces
deterministic THINKING → TEXT_DELTA → DONE events, making it useful for:

1. Testing and development without LLM dependencies
2. Placeholder agents in workflow definitions
3. Integration testing in Docker environments

Register with name "default" so it's always available.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    StateSnapshot,
)


class DefaultAdapter:
    """Built-in framework adapter with deterministic behavior.

    Each agent yields THINKING → TEXT_DELTA → DONE events.
    The output text includes the agent name and input context.
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentSpec] = {}
        self._states: dict[str, dict[str, Any]] = {}

    @property
    def name(self) -> str:
        return "default"

    async def create_agent(self, spec: AgentSpec) -> str:
        self._agents[spec.name] = spec
        self._states[spec.name] = {}
        return spec.name

    async def execute(
        self, agent: str, input: AgentInput
    ) -> AsyncIterator[AgentEvent]:
        spec = self._agents.get(agent)
        agent_name = spec.name if spec else agent

        yield AgentEvent(
            type=AgentEventType.THINKING,
            data={"text": f"Agent '{agent_name}' is thinking..."},
            agent_name=agent_name,
            timestamp=time.time(),
        )

        # Build output from input context
        user_msg = ""
        for msg in (input.messages or []):
            if isinstance(msg, dict) and msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break

        output_text = f"Output from {agent_name}"
        if user_msg:
            output_text += f": processed '{user_msg}'"

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

    async def checkpoint(self, agent: str) -> StateSnapshot:
        return StateSnapshot(
            agent_name=agent,
            state=dict(self._states.get(agent, {})),
        )

    async def restore(self, agent: str, snapshot: StateSnapshot) -> None:
        self._states[agent] = dict(snapshot.state)

    async def teardown(self, agent: str) -> None:
        self._agents.pop(agent, None)
        self._states.pop(agent, None)
