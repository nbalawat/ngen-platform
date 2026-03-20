"""LangGraph FrameworkAdapter implementation.

This adapter translates NGEN AgentSpec into LangGraph-based agents.
It uses LangGraph's StateGraph to build a simple ReAct-style agent with
tool-calling support.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
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
# Internal types
# ---------------------------------------------------------------------------

# State keys used in the LangGraph state graph
_STATE_MESSAGES = "messages"
_STATE_AGENT_NAME = "agent_name"


def _tool_spec_to_langchain(spec: ToolSpec) -> StructuredTool:
    """Convert an NGEN ToolSpec into a LangChain StructuredTool.

    For now, tools call a placeholder that returns a JSON string.
    In production, the handler would route to an MCP server or local function.
    """

    async def _placeholder_handler(**kwargs: Any) -> str:
        return json.dumps({"result": f"Tool '{spec.name}' called", "input": kwargs})

    return StructuredTool.from_function(
        func=None,
        coroutine=_placeholder_handler,
        name=spec.name,
        description=spec.description or f"Tool: {spec.name}",
        args_schema=None,
    )


def _build_messages(spec: AgentSpec, agent_input: AgentInput) -> list[BaseMessage]:
    """Convert AgentSpec system prompt + AgentInput messages into LangChain messages."""
    msgs: list[BaseMessage] = []
    if spec.system_prompt:
        msgs.append(SystemMessage(content=spec.system_prompt))
    for msg in agent_input.messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            msgs.append(AIMessage(content=content))
        else:
            msgs.append(HumanMessage(content=content))
    return msgs


# ---------------------------------------------------------------------------
# LangGraph agent wrapper
# ---------------------------------------------------------------------------


class LangGraphAgent:
    """Internal wrapper holding a compiled LangGraph and associated metadata."""

    def __init__(
        self,
        spec: AgentSpec,
        graph: CompiledStateGraph,
        tools: list[StructuredTool],
    ) -> None:
        self.spec = spec
        self.graph = graph
        self.tools = tools
        self.agent_id = str(uuid.uuid4())
        self._state: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return self.spec.name


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class LangGraphAdapter:
    """FrameworkAdapter implementation for LangGraph.

    Creates ReAct-style agents backed by LangGraph's StateGraph.
    """

    @property
    def name(self) -> str:
        return "langgraph"

    async def create_agent(self, spec: AgentSpec) -> LangGraphAgent:
        """Build a compiled LangGraph from the given AgentSpec."""
        tools = [_tool_spec_to_langchain(t) for t in spec.tools]

        # Build a minimal state graph: agent_node → END
        builder = StateGraph(state_schema=dict)

        async def agent_node(state: dict[str, Any]) -> dict[str, Any]:
            """Core agent node — processes messages and returns response."""
            messages = state.get(_STATE_MESSAGES, [])
            # In a production setup, this node would invoke the LLM via
            # langchain_core's ChatModel. For the reference implementation,
            # we produce a deterministic response so tests are repeatable.
            last_content = ""
            if messages:
                last_msg = messages[-1]
                last_content = (
                    last_msg.content if isinstance(last_msg, BaseMessage) else str(last_msg)
                )

            response = AIMessage(
                content=f"[{spec.name}] Processed: {last_content}",
            )
            return {_STATE_MESSAGES: [*messages, response]}

        builder.add_node("agent", agent_node)
        builder.set_entry_point("agent")
        builder.add_edge("agent", END)

        graph = builder.compile()

        return LangGraphAgent(spec=spec, graph=graph, tools=tools)

    async def execute(
        self,
        agent: LangGraphAgent,
        input: AgentInput,
    ) -> AsyncIterator[AgentEvent]:
        """Execute the agent graph and yield streaming events."""
        messages = _build_messages(agent.spec, input)

        yield AgentEvent(
            type=AgentEventType.TEXT_DELTA,
            data={"text": f"Starting agent '{agent.name}'..."},
            agent_name=agent.name,
            timestamp=time.time(),
        )

        initial_state = {_STATE_MESSAGES: messages}

        try:
            result = await agent.graph.ainvoke(initial_state)
            agent._state = result

            # Extract the final AI response
            result_messages = result.get(_STATE_MESSAGES, [])
            if result_messages:
                last = result_messages[-1]
                content = last.content if isinstance(last, BaseMessage) else str(last)
                yield AgentEvent(
                    type=AgentEventType.TEXT_DELTA,
                    data={"text": content},
                    agent_name=agent.name,
                    timestamp=time.time(),
                )

        except Exception as exc:
            yield AgentEvent(
                type=AgentEventType.ERROR,
                data={"error": str(exc)},
                agent_name=agent.name,
                timestamp=time.time(),
            )

        yield AgentEvent(
            type=AgentEventType.DONE,
            data={},
            agent_name=agent.name,
            timestamp=time.time(),
        )

    async def checkpoint(self, agent: LangGraphAgent) -> StateSnapshot:
        """Capture agent state as a serializable snapshot."""
        # Serialize LangChain messages to dicts
        serialized_messages = []
        for msg in agent._state.get(_STATE_MESSAGES, []):
            if isinstance(msg, BaseMessage):
                serialized_messages.append({"type": type(msg).__name__, "content": msg.content})
            else:
                serialized_messages.append({"type": "unknown", "content": str(msg)})

        return StateSnapshot(
            agent_name=agent.name,
            state={"messages": serialized_messages, "agent_id": agent.agent_id},
            version=1,
        )

    async def restore(self, agent: LangGraphAgent, snapshot: StateSnapshot) -> None:
        """Restore agent state from a snapshot."""
        messages: list[BaseMessage] = []
        for msg_dict in snapshot.state.get("messages", []):
            msg_type = msg_dict.get("type", "")
            content = msg_dict.get("content", "")
            if msg_type == "HumanMessage":
                messages.append(HumanMessage(content=content))
            elif msg_type == "AIMessage":
                messages.append(AIMessage(content=content))
            elif msg_type == "SystemMessage":
                messages.append(SystemMessage(content=content))
            else:
                messages.append(HumanMessage(content=content))
        agent._state = {_STATE_MESSAGES: messages}

    async def teardown(self, agent: LangGraphAgent) -> None:
        """Clean up agent resources."""
        agent._state = {}
        logger.info("Torn down agent: %s", agent.name)
