"""Microsoft Agent Framework adapter implementation.

Microsoft's Semantic Kernel / Agent Framework uses a plugin-based pattern
where agents are orchestrated through planners and kernels. Key concepts:

  1. Kernel — the core runtime that manages plugins and services
  2. Plugins — collections of functions (tools) the agent can call
  3. Planner — decides which plugins/functions to invoke for a task
  4. Chat completion — generates responses using configured AI service

This adapter models the Semantic Kernel pattern:
  - Agent spec maps to a Kernel with plugins
  - Tools map to KernelFunctions within plugins
  - Execution follows: plan → invoke functions → respond
  - State includes kernel configuration and chat history

Uses placeholder implementations for deterministic testing without
Azure OpenAI or other service dependencies.
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


async def _execute_function(tool: ToolSpec, arguments: dict[str, Any]) -> str:
    """Execute a kernel function and return the result."""
    return json.dumps({"result": f"Function '{tool.name}' invoked", "input": arguments})


# ---------------------------------------------------------------------------
# Semantic Kernel agent wrapper
# ---------------------------------------------------------------------------


@dataclass
class KernelPlugin:
    """Represents a Semantic Kernel plugin (collection of functions)."""

    name: str
    functions: list[ToolSpec] = field(default_factory=list)


@dataclass
class MSAFAgent:
    """Internal wrapper holding Microsoft Agent Framework agent state."""

    spec: AgentSpec
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kernel_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    plugins: list[KernelPlugin] = field(default_factory=list)
    chat_history: list[dict[str, Any]] = field(default_factory=list)
    planner_type: str = "sequential"  # sequential | stepwise
    max_turns: int = 25
    _turn_count: int = 0

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def all_functions(self) -> list[ToolSpec]:
        """All functions across all plugins."""
        return [f for p in self.plugins for f in p.functions]


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class MSAgentFrameworkAdapter:
    """FrameworkAdapter implementation for Microsoft Agent Framework.

    Implements Semantic Kernel's plugin-based pattern:
    - Agent is configured with a Kernel containing plugins
    - Planner decides which functions to call
    - Functions execute and results feed back into the conversation
    - Chat history maintains multi-turn state
    """

    @property
    def name(self) -> str:
        return "ms-agent-framework"

    async def create_agent(self, spec: AgentSpec) -> MSAFAgent:
        """Create a Microsoft Agent Framework agent from AgentSpec."""
        max_turns = spec.decision_loop.get("max_turns", 25) if spec.decision_loop else 25
        planner = spec.metadata.get("planner", "sequential") if spec.metadata else "sequential"

        # Group tools into a default plugin
        default_plugin = KernelPlugin(
            name="default",
            functions=list(spec.tools),
        )

        return MSAFAgent(
            spec=spec,
            plugins=[default_plugin] if spec.tools else [],
            planner_type=planner,
            max_turns=max_turns,
        )

    async def execute(
        self,
        agent: MSAFAgent,
        input: AgentInput,
    ) -> AsyncIterator[AgentEvent]:
        """Execute the agent and yield streaming events."""
        agent._turn_count = 0

        # Update chat history
        for msg in input.messages:
            agent.chat_history.append(msg)

        # Extract user content
        last_user_content = ""
        for msg in reversed(input.messages):
            if msg.get("role") == "user":
                last_user_content = msg["content"]
                break

        # Planning phase — planner analyzes available functions
        yield AgentEvent(
            type=AgentEventType.THINKING,
            data={
                "text": f"[{agent.planner_type} planner] Creating plan for: {last_user_content[:80]}",
                "planner": agent.planner_type,
                "kernel_id": agent.kernel_id,
                "available_plugins": [p.name for p in agent.plugins],
            },
            agent_name=agent.name,
            timestamp=time.time(),
        )

        # Function invocation phase
        function_results: list[str] = []
        for function in agent.all_functions:
            if agent._turn_count >= agent.max_turns:
                yield AgentEvent(
                    type=AgentEventType.ERROR,
                    data={"error": f"Max turns ({agent.max_turns}) exceeded"},
                    agent_name=agent.name,
                    timestamp=time.time(),
                )
                break

            agent._turn_count += 1
            call_id = str(uuid.uuid4())[:8]

            yield AgentEvent(
                type=AgentEventType.TOOL_CALL_START,
                data={
                    "tool": function.name,
                    "tool_call_id": call_id,
                    "arguments": {"input": last_user_content},
                    "plugin": "default",
                },
                agent_name=agent.name,
                timestamp=time.time(),
            )

            try:
                result = await _execute_function(function, {"input": last_user_content})
                function_results.append(result)

                yield AgentEvent(
                    type=AgentEventType.TOOL_CALL_END,
                    data={
                        "tool": function.name,
                        "tool_call_id": call_id,
                        "result": result,
                    },
                    agent_name=agent.name,
                    timestamp=time.time(),
                )
            except Exception as exc:
                yield AgentEvent(
                    type=AgentEventType.ERROR,
                    data={"error": f"Function '{function.name}' failed: {exc}"},
                    agent_name=agent.name,
                    timestamp=time.time(),
                )

        # Cost checkpoint
        yield AgentEvent(
            type=AgentEventType.COST_CHECKPOINT,
            data={
                "turns": agent._turn_count,
                "functions_called": len(function_results),
                "kernel_id": agent.kernel_id,
            },
            agent_name=agent.name,
            timestamp=time.time(),
        )

        # Generate response
        fn_context = ""
        if function_results:
            fn_names = ", ".join(f.name for f in agent.all_functions)
            fn_context = f" [functions: {fn_names}]"

        response_text = (
            f"Processed '{last_user_content}' using {agent.planner_type} "
            f"planner{fn_context}."
        )

        yield AgentEvent(
            type=AgentEventType.RESPONSE,
            data={
                "text": response_text,
                "kernel_id": agent.kernel_id,
                "planner": agent.planner_type,
            },
            agent_name=agent.name,
            timestamp=time.time(),
        )

        agent.chat_history.append({"role": "assistant", "content": response_text})

        yield AgentEvent(
            type=AgentEventType.DONE,
            data={"kernel_id": agent.kernel_id},
            agent_name=agent.name,
            timestamp=time.time(),
        )

    async def checkpoint(self, agent: MSAFAgent) -> StateSnapshot:
        """Capture agent state as a serializable snapshot."""
        return StateSnapshot(
            agent_name=agent.name,
            state={
                "chat_history": agent.chat_history,
                "agent_id": agent.agent_id,
                "kernel_id": agent.kernel_id,
                "planner_type": agent.planner_type,
                "turn_count": agent._turn_count,
                "plugins": [
                    {
                        "name": p.name,
                        "functions": [f.name for f in p.functions],
                    }
                    for p in agent.plugins
                ],
            },
            version=1,
        )

    async def restore(self, agent: MSAFAgent, snapshot: StateSnapshot) -> None:
        """Restore agent state from a snapshot."""
        agent.chat_history = snapshot.state.get("chat_history", [])
        agent._turn_count = snapshot.state.get("turn_count", 0)
        agent.planner_type = snapshot.state.get("planner", agent.planner_type)
        agent.kernel_id = snapshot.state.get("kernel_id", agent.kernel_id)

    async def teardown(self, agent: MSAFAgent) -> None:
        """Clean up agent resources."""
        agent.chat_history = []
        agent._turn_count = 0
        logger.info("Torn down MS Agent Framework agent: %s (kernel: %s)", agent.name, agent.kernel_id)
