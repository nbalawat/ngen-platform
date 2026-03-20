"""Google ADK FrameworkAdapter implementation.

The Google Agent Development Kit (ADK) uses a function-calling pattern
where agents are defined by their tools and instructions. The agent
receives user input, decides which tools to call, processes results,
and formulates a response.

Key ADK concepts modeled here:
  1. Agent has instructions (system prompt) and available tools
  2. Execution follows: plan → tool calls → synthesize response
  3. Sessions maintain conversation state across interactions
  4. Sub-agents can be delegated to for specialized tasks

This adapter uses placeholder tool handlers so tests are deterministic
without requiring Google Cloud credentials or API keys.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    StateSnapshot,
    ToolSpec,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


async def _execute_tool(tool: ToolSpec, arguments: dict[str, Any]) -> str:
    """Execute a tool and return the result as a string."""
    return json.dumps({"result": f"Tool '{tool.name}' executed", "input": arguments})


# ---------------------------------------------------------------------------
# ADK agent wrapper
# ---------------------------------------------------------------------------


@dataclass
class ADKSession:
    """Represents an ADK session for state management."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ADKAgent:
    """Internal wrapper holding Google ADK agent state."""

    spec: AgentSpec
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    instructions: str = ""
    tools: list[ToolSpec] = field(default_factory=list)
    session: ADKSession = field(default_factory=ADKSession)
    sub_agents: list[str] = field(default_factory=list)
    max_turns: int = 25
    _turn_count: int = 0

    @property
    def name(self) -> str:
        return self.spec.name


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class GoogleADKAdapter:
    """FrameworkAdapter implementation for Google ADK.

    Implements Google's function-calling agent pattern:
    - Agent receives instructions and available tools
    - Plans which tools to call based on user input
    - Executes tools and synthesizes results
    - Maintains session history for multi-turn conversations
    """

    @property
    def name(self) -> str:
        return "google-adk"

    async def create_agent(self, spec: AgentSpec) -> ADKAgent:
        """Create a Google ADK agent from the given AgentSpec."""
        max_turns = spec.decision_loop.get("max_turns", 25) if spec.decision_loop else 25

        # Map sub-agents from metadata
        sub_agents = spec.metadata.get("sub_agents", []) if spec.metadata else []

        return ADKAgent(
            spec=spec,
            instructions=spec.system_prompt or f"You are {spec.name}, a helpful agent.",
            tools=list(spec.tools),
            sub_agents=sub_agents,
            max_turns=max_turns,
        )

    async def execute(
        self,
        agent: ADKAgent,
        input: AgentInput,
    ) -> AsyncIterator[AgentEvent]:
        """Execute the ADK agent and yield streaming events."""
        agent._turn_count = 0

        # Update session history
        for msg in input.messages:
            agent.session.history.append(msg)

        # Extract user content
        last_user_content = ""
        for msg in reversed(input.messages):
            if msg.get("role") == "user":
                last_user_content = msg["content"]
                break

        # Planning phase — ADK agents plan before executing
        yield AgentEvent(
            type=AgentEventType.THINKING,
            data={
                "text": f"Planning: analyzing '{last_user_content[:80]}...'",
                "instructions": agent.instructions[:100],
                "available_tools": [t.name for t in agent.tools],
            },
            agent_name=agent.name,
            timestamp=time.time(),
        )

        # Tool execution phase
        tool_results: list[str] = []
        for tool in agent.tools:
            if agent._turn_count >= agent.max_turns:
                yield AgentEvent(
                    type=AgentEventType.ERROR,
                    data={"error": f"Max turns ({agent.max_turns}) exceeded"},
                    agent_name=agent.name,
                    timestamp=time.time(),
                )
                break

            agent._turn_count += 1
            tool_call_id = str(uuid.uuid4())[:8]

            yield AgentEvent(
                type=AgentEventType.TOOL_CALL_START,
                data={
                    "tool": tool.name,
                    "tool_call_id": tool_call_id,
                    "arguments": {"query": last_user_content},
                },
                agent_name=agent.name,
                timestamp=time.time(),
            )

            try:
                result = await _execute_tool(tool, {"query": last_user_content})
                tool_results.append(result)

                yield AgentEvent(
                    type=AgentEventType.TOOL_CALL_END,
                    data={
                        "tool": tool.name,
                        "tool_call_id": tool_call_id,
                        "result": result,
                    },
                    agent_name=agent.name,
                    timestamp=time.time(),
                )
            except Exception as exc:
                yield AgentEvent(
                    type=AgentEventType.ERROR,
                    data={"error": f"Tool '{tool.name}' failed: {exc}"},
                    agent_name=agent.name,
                    timestamp=time.time(),
                )

        # Cost checkpoint
        yield AgentEvent(
            type=AgentEventType.COST_CHECKPOINT,
            data={
                "turns": agent._turn_count,
                "tools_called": len(tool_results),
                "session_id": agent.session.session_id,
            },
            agent_name=agent.name,
            timestamp=time.time(),
        )

        # Synthesize response
        tool_context = ""
        if tool_results:
            tool_names = ", ".join(t.name for t in agent.tools)
            tool_context = f" [tools: {tool_names}]"

        response_text = (
            f"Based on analysis of '{last_user_content}', "
            f"here is the result{tool_context}."
        )

        yield AgentEvent(
            type=AgentEventType.RESPONSE,
            data={
                "text": response_text,
                "session_id": agent.session.session_id,
            },
            agent_name=agent.name,
            timestamp=time.time(),
        )

        agent.session.history.append({"role": "assistant", "content": response_text})

        yield AgentEvent(
            type=AgentEventType.DONE,
            data={"session_id": agent.session.session_id},
            agent_name=agent.name,
            timestamp=time.time(),
        )

    async def checkpoint(self, agent: ADKAgent) -> StateSnapshot:
        """Capture agent state as a serializable snapshot."""
        return StateSnapshot(
            agent_name=agent.name,
            state={
                "session": {
                    "session_id": agent.session.session_id,
                    "history": agent.session.history,
                    "metadata": agent.session.metadata,
                },
                "agent_id": agent.agent_id,
                "instructions": agent.instructions,
                "sub_agents": agent.sub_agents,
                "turn_count": agent._turn_count,
            },
            version=1,
        )

    async def restore(self, agent: ADKAgent, snapshot: StateSnapshot) -> None:
        """Restore agent state from a snapshot."""
        agent._turn_count = snapshot.state.get("turn_count", 0)
        agent.instructions = snapshot.state.get("instructions", agent.instructions)
        agent.sub_agents = snapshot.state.get("sub_agents", [])

        session_data = snapshot.state.get("session", {})
        if session_data:
            agent.session = ADKSession(
                session_id=session_data.get("session_id", agent.session.session_id),
                history=session_data.get("history", []),
                metadata=session_data.get("metadata", {}),
            )

    async def teardown(self, agent: ADKAgent) -> None:
        """Clean up agent resources."""
        agent.session.history = []
        agent._turn_count = 0
        logger.info("Torn down Google ADK agent: %s", agent.name)
