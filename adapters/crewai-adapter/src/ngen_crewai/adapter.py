"""CrewAI FrameworkAdapter implementation.

This adapter translates NGEN AgentSpec into CrewAI-style agents. CrewAI uses
a role-based multi-agent pattern where each agent has a role, goal, and
backstory, and collaborates through task delegation.

The adapter implements the crew pattern:
  1. Agent receives a role (from spec name) and goal (from system prompt)
  2. Agent processes tasks by reasoning about its role
  3. Tools are executed as part of task completion
  4. Results include the agent's role-based perspective

Like the other adapters, this uses placeholder tool handlers so tests are
deterministic without requiring external dependencies or API keys.
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
# CrewAI agent wrapper
# ---------------------------------------------------------------------------


@dataclass
class CrewRole:
    """Represents a CrewAI agent role configuration."""

    role: str
    goal: str
    backstory: str
    verbose: bool = True


@dataclass
class CrewTask:
    """A task assigned to a crew member."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    expected_output: str = ""
    result: str | None = None


@dataclass
class CrewAgent:
    """Internal wrapper holding crew member state and configuration."""

    spec: AgentSpec
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    role: CrewRole = field(default_factory=lambda: CrewRole("", "", ""))
    tools: list[ToolSpec] = field(default_factory=list)
    tasks: list[CrewTask] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    max_turns: int = 25
    _turn_count: int = 0

    @property
    def name(self) -> str:
        return self.spec.name


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class CrewAIAdapter:
    """FrameworkAdapter implementation for CrewAI.

    Implements a role-based agent pattern:
    - Each agent has a role, goal, and backstory derived from the AgentSpec
    - Tasks are processed through the agent's role-based perspective
    - Tools are called as part of task execution
    - Delegation events track multi-agent handoffs
    """

    @property
    def name(self) -> str:
        return "crewai"

    async def create_agent(self, spec: AgentSpec) -> CrewAgent:
        """Create a CrewAI agent from the given AgentSpec."""
        max_turns = spec.decision_loop.get("max_turns", 25) if spec.decision_loop else 25

        # Map AgentSpec to CrewAI role pattern
        role = CrewRole(
            role=spec.name.replace("-", " ").title(),
            goal=spec.system_prompt or f"Execute tasks as {spec.name}",
            backstory=spec.description or f"An agent named {spec.name}",
        )

        return CrewAgent(
            spec=spec,
            role=role,
            tools=list(spec.tools),
            max_turns=max_turns,
        )

    async def execute(
        self,
        agent: CrewAgent,
        input: AgentInput,
    ) -> AsyncIterator[AgentEvent]:
        """Execute the crew agent and yield streaming events."""
        agent._turn_count = 0
        agent.messages = list(input.messages)

        # Extract user content
        last_user_content = ""
        for msg in reversed(input.messages):
            if msg.get("role") == "user":
                last_user_content = msg["content"]
                break

        # Create a task from the input
        task = CrewTask(
            description=last_user_content,
            expected_output="Processed result",
        )
        agent.tasks.append(task)

        # Emit thinking event with role context
        yield AgentEvent(
            type=AgentEventType.THINKING,
            data={
                "text": (
                    f"[{agent.role.role}] Analyzing task: "
                    f"{task.description[:100]}..."
                ),
                "role": agent.role.role,
                "goal": agent.role.goal,
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
                "task_id": task.id,
            },
            agent_name=agent.name,
            timestamp=time.time(),
        )

        # Generate role-based response
        tool_context = ""
        if tool_results:
            tool_names = ", ".join(t.name for t in agent.tools)
            tool_context = f" (tools used: {tool_names})"

        response_text = (
            f"[{agent.role.role}] Task completed: "
            f"{last_user_content}{tool_context}"
        )
        task.result = response_text

        yield AgentEvent(
            type=AgentEventType.RESPONSE,
            data={
                "text": response_text,
                "role": agent.role.role,
                "task_id": task.id,
            },
            agent_name=agent.name,
            timestamp=time.time(),
        )

        agent.messages.append({"role": "assistant", "content": response_text})

        yield AgentEvent(
            type=AgentEventType.DONE,
            data={"task_id": task.id},
            agent_name=agent.name,
            timestamp=time.time(),
        )

    async def checkpoint(self, agent: CrewAgent) -> StateSnapshot:
        """Capture agent state as a serializable snapshot."""
        return StateSnapshot(
            agent_name=agent.name,
            state={
                "messages": agent.messages,
                "role": {
                    "role": agent.role.role,
                    "goal": agent.role.goal,
                    "backstory": agent.role.backstory,
                },
                "tasks": [
                    {
                        "id": t.id,
                        "description": t.description,
                        "expected_output": t.expected_output,
                        "result": t.result,
                    }
                    for t in agent.tasks
                ],
                "agent_id": agent.agent_id,
                "turn_count": agent._turn_count,
            },
            version=1,
        )

    async def restore(self, agent: CrewAgent, snapshot: StateSnapshot) -> None:
        """Restore agent state from a snapshot."""
        agent.messages = snapshot.state.get("messages", [])
        agent._turn_count = snapshot.state.get("turn_count", 0)

        role_data = snapshot.state.get("role", {})
        if role_data:
            agent.role = CrewRole(
                role=role_data.get("role", ""),
                goal=role_data.get("goal", ""),
                backstory=role_data.get("backstory", ""),
            )

        agent.tasks = [
            CrewTask(
                id=t.get("id", ""),
                description=t.get("description", ""),
                expected_output=t.get("expected_output", ""),
                result=t.get("result"),
            )
            for t in snapshot.state.get("tasks", [])
        ]

    async def teardown(self, agent: CrewAgent) -> None:
        """Clean up agent resources."""
        agent.messages = []
        agent.tasks = []
        agent._turn_count = 0
        logger.info("Torn down CrewAI agent: %s (role: %s)", agent.name, agent.role.role)
