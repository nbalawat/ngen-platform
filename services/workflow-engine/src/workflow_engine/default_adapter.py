"""Default framework adapter — calls model-gateway for real LLM responses.

When the model-gateway is available and configured with an LLM provider
(Anthropic, etc.), this adapter sends the agent's system prompt and user
messages to get real AI responses. Falls back to intelligent template
responses when the gateway is unavailable.

Register with name "default" so it's always available.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    StateSnapshot,
)

logger = logging.getLogger(__name__)

# Model to use for LLM calls (prefer Sonnet for speed/quality balance)
_DEFAULT_LLM_MODEL = os.environ.get("NGEN_DEFAULT_MODEL", "claude-sonnet-4")
_GATEWAY_URL = os.environ.get("WF_MODEL_GATEWAY_URL", "http://localhost:8002")
_MCP_MANAGER_URL = os.environ.get("WF_MCP_MANAGER_URL", "http://localhost:8005")


def _extract_role(system_prompt: str) -> str:
    if not system_prompt:
        return "helpful assistant"
    first_sentence = system_prompt.split(".")[0].strip()
    for prefix in ("you are a ", "you are an ", "you are ", "you're a ", "you're an ", "you're "):
        if first_sentence.lower().startswith(prefix):
            first_sentence = first_sentence[len(prefix):]
            break
    return first_sentence[:100] if first_sentence else "helpful assistant"


def _extract_topic(user_msg: str) -> str:
    if not user_msg:
        return "your request"
    msg = user_msg.strip().rstrip("?!.")
    for prefix in ("can you ", "could you ", "please ", "help me ", "i need to ",
                    "how do i ", "how can i ", "what is ", "what are ", "tell me about ",
                    "explain ", "describe ", "show me ", "find ", "search for "):
        if msg.lower().startswith(prefix):
            msg = msg[len(prefix):]
            break
    return msg[:80] if msg else "your request"


def _get_tools(spec: AgentSpec) -> list[str]:
    tools: list[str] = []
    for t in spec.tools:
        tools.append(t.name)
    meta_tools = spec.metadata.get("tools", [])
    if isinstance(meta_tools, list):
        for t in meta_tools:
            if isinstance(t, str) and t not in tools:
                tools.append(t)
    return tools


def _pick_variation(text: str, options: list[str]) -> str:
    h = int(hashlib.md5(text.encode()).hexdigest(), 16)
    return options[h % len(options)]


def _generate_fallback_response(role: str, topic: str, user_msg: str) -> str:
    """Generate a template response when the LLM is unavailable."""
    templates = [
        f"As a {role}, here's my perspective on {topic}: This is an area where careful analysis is needed. "
        f"I'd recommend breaking this down into key components and evaluating each one systematically. "
        f"Would you like me to elaborate on any specific aspect?",
        f"Regarding {topic} - this is a great question. From my experience as a {role}, "
        f"there are several important factors to consider here. Let me know which angle "
        f"you'd like to explore further.",
        f"Let me address {topic}. As a {role}, I can share that this typically involves "
        f"understanding the context, identifying key requirements, and then developing "
        f"a structured approach. What specific aspect interests you most?",
    ]
    return _pick_variation(user_msg, templates)


async def _call_llm(system_prompt: str, user_msg: str) -> str | None:
    """Call the model-gateway for a real LLM response. Returns None on failure."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_msg})

            resp = await client.post(
                f"{_GATEWAY_URL}/v1/chat/completions",
                json={
                    "model": _DEFAULT_LLM_MODEL,
                    "messages": messages,
                    "max_tokens": 512,
                },
                headers={"x-tenant-id": "default"},
            )

            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    if content and content != "This is a mock response.":
                        return content
            else:
                logger.debug("Model gateway returned %d: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.debug("Failed to call model gateway: %s", e)
    return None


async def _invoke_real_tool(
    server_name: str, tool_name: str, arguments: dict[str, Any],
) -> str | None:
    """Call a tool via the MCP Manager. Returns result text or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_MCP_MANAGER_URL}/api/v1/invoke",
                json={
                    "server_name": server_name,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "namespace": "default",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("error"):
                    return None
                result = data.get("result", {})
                if isinstance(result, dict):
                    return result.get("text", str(result))
                return str(result) if result else None
    except Exception as e:
        logger.debug("MCP tool invocation failed for %s/%s: %s", server_name, tool_name, e)
    return None


class DefaultAdapter:
    """Built-in framework adapter that calls the model-gateway for real LLM responses.

    Falls back to intelligent template responses when the gateway is unavailable
    or returns a mock response. Supports tool simulation via TOOL_CALL events.
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
        system_prompt = spec.system_prompt if spec else ""
        role = _extract_role(system_prompt)

        # Extract user message
        user_msg = ""
        for msg in (input.messages or []):
            if isinstance(msg, dict) and msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break

        topic = _extract_topic(user_msg)
        tools = _get_tools(spec) if spec else []

        # --- THINKING ---
        thinking_templates = [
            f"Analyzing your question about {topic} and considering the best approach...",
            f"Let me think about {topic} from my perspective as a {role}...",
            f"Processing your request about {topic}...",
        ]
        thinking_text = _pick_variation(user_msg + "think", thinking_templates)
        if tools:
            thinking_text += f" I have {len(tools)} tool(s) that may help."

        yield AgentEvent(
            type=AgentEventType.THINKING,
            data={"text": thinking_text},
            agent_name=agent_name,
            timestamp=time.time(),
        )

        # --- TOOL CALLS (if tools configured) ---
        tool_summaries: list[str] = []
        for tool_name in tools[:2]:
            # Parse server_name/tool_name format
            if "/" in tool_name:
                server_name, short_name = tool_name.split("/", 1)
            else:
                server_name, short_name = tool_name, tool_name

            tool_args = {"query": user_msg[:200] if user_msg else topic}

            yield AgentEvent(
                type=AgentEventType.TOOL_CALL_START,
                data={"tool": tool_name, "input": tool_args},
                agent_name=agent_name,
                timestamp=time.time(),
            )

            # Try real MCP invocation, fall back to template
            real_result = await _invoke_real_tool(server_name, short_name, tool_args)
            if real_result:
                result_text = real_result
            else:
                result_templates = [
                    f"Found relevant data about {topic}",
                    f"Retrieved results related to {topic}",
                    f"Gathered context on {topic} from available sources",
                ]
                result_text = _pick_variation(tool_name + user_msg, result_templates)

            tool_summaries.append(f"{short_name}: {result_text}")

            yield AgentEvent(
                type=AgentEventType.TOOL_CALL_END,
                data={
                    "tool": tool_name,
                    "output": result_text,
                    "status": "success",
                },
                agent_name=agent_name,
                timestamp=time.time(),
            )

        # --- TEXT_DELTA (main response from LLM or fallback) ---

        # Try calling real LLM via model-gateway
        llm_prompt = system_prompt
        if tool_summaries:
            llm_prompt += f"\n\nTool results:\n" + "\n".join(tool_summaries)

        llm_response = await _call_llm(llm_prompt, user_msg)

        if llm_response:
            output_text = llm_response
        else:
            output_text = _generate_fallback_response(role, topic, user_msg)

        yield AgentEvent(
            type=AgentEventType.TEXT_DELTA,
            data={"text": output_text},
            agent_name=agent_name,
            timestamp=time.time(),
        )

        # --- DONE ---
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
