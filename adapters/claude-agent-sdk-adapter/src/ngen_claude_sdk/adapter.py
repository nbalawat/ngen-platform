"""Claude Agent SDK FrameworkAdapter implementation.

This adapter translates NGEN AgentSpec into Claude-native agentic loops.
It implements a tool-use loop pattern aligned with the Anthropic Messages API:

  1. Send messages to the model
  2. If the model calls tools → execute them, append results, loop back
  3. If the model produces text → yield it as a response, done

The adapter does NOT require the `anthropic` SDK at runtime. Instead it defines
the agent structure and event streaming contract, delegating actual LLM calls
to the model-gateway service via the platform's HTTP routing. This means the
adapter works with any backend the model-gateway supports (Anthropic, mock-llm,
Ollama, etc.) and can be tested without API keys.

For the reference implementation, tool calls use placeholder handlers (same
pattern as the LangGraph adapter) so tests are deterministic and repeatable.
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
    """Execute a tool and return the result as a string.

    In production, this would route to an MCP server or local handler.
    For the reference implementation, it returns a deterministic response.
    """
    if tool.handler:
        # Future: dynamically import and call the handler
        pass
    return json.dumps({"result": f"Tool '{tool.name}' executed", "input": arguments})


def _build_tool_definitions(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """Convert NGEN ToolSpecs to Claude-native tool definitions."""
    return [
        {
            "name": tool.name,
            "description": tool.description or f"Tool: {tool.name}",
            "input_schema": tool.parameters or {"type": "object", "properties": {}},
        }
        for tool in tools
    ]


# ---------------------------------------------------------------------------
# Message conversion
# ---------------------------------------------------------------------------


def _build_messages(
    spec: AgentSpec, agent_input: AgentInput
) -> tuple[str, list[dict[str, Any]]]:
    """Convert AgentSpec and AgentInput into Claude-native message format.

    Returns (system_prompt, messages) where messages follow the Anthropic
    Messages API structure.
    """
    system_prompt = spec.system_prompt or ""
    messages: list[dict[str, Any]] = []

    for msg in agent_input.messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # Claude API only supports "user" and "assistant" roles in messages
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})
        else:
            messages.append({"role": "user", "content": content})

    return system_prompt, messages


# ---------------------------------------------------------------------------
# Agent wrapper
# ---------------------------------------------------------------------------


@dataclass
class ClaudeAgent:
    """Internal wrapper holding agent state and configuration."""

    spec: AgentSpec
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tools: list[ToolSpec] = field(default_factory=list)
    tool_definitions: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    system_prompt: str = ""
    max_turns: int = 25
    _turn_count: int = 0

    @property
    def name(self) -> str:
        return self.spec.name


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class ClaudeAgentSDKAdapter:
    """FrameworkAdapter implementation for Claude Agent SDK.

    Implements a tool-use agentic loop:
    - Agent receives messages and decides to call tools or respond
    - Tool results are appended as user messages and the loop continues
    - Decision loop is bounded by max_turns from the AgentSpec
    - Events are streamed for each step (thinking, tool calls, responses)
    """

    @property
    def name(self) -> str:
        return "claude-agent-sdk"

    async def create_agent(self, spec: AgentSpec) -> ClaudeAgent:
        """Create a Claude agent from the given AgentSpec."""
        max_turns = spec.decision_loop.get("max_turns", 25) if spec.decision_loop else 25

        return ClaudeAgent(
            spec=spec,
            tools=list(spec.tools),
            tool_definitions=_build_tool_definitions(spec.tools),
            system_prompt=spec.system_prompt or "",
            max_turns=max_turns,
        )

    async def execute(
        self,
        agent: ClaudeAgent,
        input: AgentInput,
    ) -> AsyncIterator[AgentEvent]:
        """Execute the agent loop and yield streaming events.

        The loop simulates Claude's tool-use pattern:
        1. Process input messages
        2. If tools are available, simulate a tool call on the first turn
        3. Process tool results
        4. Produce final response
        """
        system_prompt, messages = _build_messages(agent.spec, input)
        agent.system_prompt = system_prompt
        agent.messages = messages
        agent._turn_count = 0

        # Yield thinking event
        yield AgentEvent(
            type=AgentEventType.THINKING,
            data={"text": f"Agent '{agent.name}' analyzing input..."},
            agent_name=agent.name,
            timestamp=time.time(),
        )

        # Extract user's last message for response generation
        last_user_content = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                last_user_content = msg["content"]
                break

        # Tool-use loop
        if agent.tools:
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

                # Emit tool call start
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

                # Execute tool
                try:
                    result = await _execute_tool(
                        tool, {"query": last_user_content}
                    )

                    # Emit tool call end
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

                    # Append tool result to conversation
                    agent.messages.append({
                        "role": "assistant",
                        "content": json.dumps({
                            "type": "tool_use",
                            "name": tool.name,
                            "input": {"query": last_user_content},
                        }),
                    })
                    agent.messages.append({
                        "role": "user",
                        "content": json.dumps({
                            "type": "tool_result",
                            "tool_use_id": tool_call_id,
                            "content": result,
                        }),
                    })

                except Exception as exc:
                    yield AgentEvent(
                        type=AgentEventType.ERROR,
                        data={
                            "error": f"Tool '{tool.name}' failed: {exc}",
                            "tool": tool.name,
                        },
                        agent_name=agent.name,
                        timestamp=time.time(),
                    )

        # Yield cost checkpoint
        yield AgentEvent(
            type=AgentEventType.COST_CHECKPOINT,
            data={
                "turns": agent._turn_count,
                "tools_called": agent._turn_count,
                "estimated_tokens": len(last_user_content.split()) * 4,
            },
            agent_name=agent.name,
            timestamp=time.time(),
        )

        # Final response
        tool_context = ""
        if agent.tools:
            tool_names = ", ".join(t.name for t in agent.tools)
            tool_context = f" (used tools: {tool_names})"

        response_text = f"[{agent.name}] Processed: {last_user_content}{tool_context}"

        yield AgentEvent(
            type=AgentEventType.RESPONSE,
            data={"text": response_text},
            agent_name=agent.name,
            timestamp=time.time(),
        )

        # Append assistant response to conversation history
        agent.messages.append({"role": "assistant", "content": response_text})

        yield AgentEvent(
            type=AgentEventType.DONE,
            data={},
            agent_name=agent.name,
            timestamp=time.time(),
        )

    async def checkpoint(self, agent: ClaudeAgent) -> StateSnapshot:
        """Capture agent state as a serializable snapshot."""
        return StateSnapshot(
            agent_name=agent.name,
            state={
                "messages": agent.messages,
                "system_prompt": agent.system_prompt,
                "agent_id": agent.agent_id,
                "turn_count": agent._turn_count,
            },
            version=1,
        )

    async def restore(self, agent: ClaudeAgent, snapshot: StateSnapshot) -> None:
        """Restore agent state from a snapshot."""
        agent.messages = snapshot.state.get("messages", [])
        agent.system_prompt = snapshot.state.get("system_prompt", "")
        agent._turn_count = snapshot.state.get("turn_count", 0)

    async def teardown(self, agent: ClaudeAgent) -> None:
        """Clean up agent resources."""
        agent.messages = []
        agent._turn_count = 0
        logger.info("Torn down Claude agent: %s", agent.name)
