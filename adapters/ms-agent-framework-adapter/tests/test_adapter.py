"""Tests for Microsoft Agent Framework adapter — Semantic Kernel pattern."""

from __future__ import annotations

import pytest

from ngen_framework_core.protocols import (
    AgentEventType,
    AgentInput,
    AgentSpec,
    ModelRef,
    StateSnapshot,
    ToolSpec,
)
from ngen_msaf.adapter import MSAFAgent, MSAgentFrameworkAdapter


@pytest.fixture()
def adapter() -> MSAgentFrameworkAdapter:
    return MSAgentFrameworkAdapter()


@pytest.fixture()
def basic_spec() -> AgentSpec:
    return AgentSpec(
        name="assistant",
        description="A helpful assistant",
        framework="ms-agent-framework",
        model=ModelRef(name="gpt-4"),
        system_prompt="You are a helpful assistant.",
    )


@pytest.fixture()
def spec_with_tools() -> AgentSpec:
    return AgentSpec(
        name="plugin-agent",
        description="Agent with kernel plugins",
        framework="ms-agent-framework",
        model=ModelRef(name="gpt-4"),
        system_prompt="Use plugins to help users.",
        tools=[
            ToolSpec(name="WebSearch", description="Search the web"),
            ToolSpec(name="EmailSender", description="Send emails"),
        ],
    )


@pytest.fixture()
def user_input() -> AgentInput:
    return AgentInput(
        messages=[{"role": "user", "content": "Send an email summary of today's news"}],
    )


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestAdapterProperties:
    def test_name(self, adapter):
        assert adapter.name == "ms-agent-framework"

    async def test_create_agent(self, adapter, basic_spec):
        agent = await adapter.create_agent(basic_spec)
        assert isinstance(agent, MSAFAgent)
        assert agent.name == "assistant"
        assert agent.kernel_id  # Has a kernel ID
        assert agent.planner_type == "sequential"

    async def test_create_agent_with_tools(self, adapter, spec_with_tools):
        agent = await adapter.create_agent(spec_with_tools)
        assert len(agent.plugins) == 1
        assert agent.plugins[0].name == "default"
        assert len(agent.all_functions) == 2

    async def test_create_agent_with_stepwise_planner(self, adapter):
        spec = AgentSpec(
            name="planner-agent",
            description="Agent with stepwise planner",
            framework="ms-agent-framework",
            model=ModelRef(name="gpt-4"),
            system_prompt="Plan and execute.",
            metadata={"planner": "stepwise"},
        )
        agent = await adapter.create_agent(spec)
        assert agent.planner_type == "stepwise"


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class TestBasicExecution:
    async def test_execute_without_tools(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, user_input)]

        event_types = [e.type for e in events]
        assert AgentEventType.THINKING in event_types
        assert AgentEventType.COST_CHECKPOINT in event_types
        assert AgentEventType.RESPONSE in event_types
        assert AgentEventType.DONE in event_types

    async def test_response_references_input(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, user_input)]
        response = next(e for e in events if e.type == AgentEventType.RESPONSE)
        assert "email" in response.data["text"].lower() or "news" in response.data["text"].lower()

    async def test_all_events_have_agent_name(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, user_input)]
        assert all(e.agent_name == "assistant" for e in events)

    async def test_all_events_have_timestamp(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, user_input)]
        assert all(e.timestamp > 0 for e in events)

    async def test_thinking_includes_planner_info(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, user_input)]
        thinking = next(e for e in events if e.type == AgentEventType.THINKING)
        assert "planner" in thinking.data
        assert thinking.data["planner"] == "sequential"

    async def test_thinking_includes_kernel_id(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, user_input)]
        thinking = next(e for e in events if e.type == AgentEventType.THINKING)
        assert "kernel_id" in thinking.data


class TestToolExecution:
    async def test_function_call_events(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]

        starts = [e for e in events if e.type == AgentEventType.TOOL_CALL_START]
        ends = [e for e in events if e.type == AgentEventType.TOOL_CALL_END]
        assert len(starts) == 2
        assert len(ends) == 2

    async def test_function_call_has_plugin_name(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]
        start = next(e for e in events if e.type == AgentEventType.TOOL_CALL_START)
        assert start.data["plugin"] == "default"

    async def test_function_names_in_response(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]
        response = next(e for e in events if e.type == AgentEventType.RESPONSE)
        assert "WebSearch" in response.data["text"]

    async def test_cost_checkpoint(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]
        cost = next(e for e in events if e.type == AgentEventType.COST_CHECKPOINT)
        assert cost.data["turns"] == 2
        assert cost.data["functions_called"] == 2
        assert "kernel_id" in cost.data


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------


class TestChatHistory:
    async def test_history_updated(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        [e async for e in adapter.execute(agent, user_input)]
        assert len(agent.chat_history) >= 2
        assert agent.chat_history[0]["role"] == "user"
        assert agent.chat_history[-1]["role"] == "assistant"

    async def test_multiple_executions_accumulate(self, adapter, basic_spec):
        agent = await adapter.create_agent(basic_spec)
        input1 = AgentInput(messages=[{"role": "user", "content": "hello"}])
        input2 = AgentInput(messages=[{"role": "user", "content": "world"}])
        [e async for e in adapter.execute(agent, input1)]
        [e async for e in adapter.execute(agent, input2)]
        assert len(agent.chat_history) >= 4  # 2 user + 2 assistant


# ---------------------------------------------------------------------------
# Checkpoint / restore
# ---------------------------------------------------------------------------


class TestCheckpointRestore:
    async def test_checkpoint_captures_state(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        [e async for e in adapter.execute(agent, user_input)]
        snapshot = await adapter.checkpoint(agent)
        assert snapshot.agent_name == "assistant"
        assert "chat_history" in snapshot.state
        assert "kernel_id" in snapshot.state

    async def test_restore_recovers_state(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        [e async for e in adapter.execute(agent, user_input)]
        snapshot = await adapter.checkpoint(agent)

        agent2 = await adapter.create_agent(basic_spec)
        assert len(agent2.chat_history) == 0
        await adapter.restore(agent2, snapshot)
        assert len(agent2.chat_history) >= 2
        assert agent2.kernel_id == agent.kernel_id

    async def test_restore_from_raw_snapshot(self, adapter, basic_spec):
        agent = await adapter.create_agent(basic_spec)
        raw = StateSnapshot(
            agent_name="assistant",
            state={
                "chat_history": [{"role": "user", "content": "hi"}],
                "kernel_id": "k-42",
                "turn_count": 3,
            },
        )
        await adapter.restore(agent, raw)
        assert agent.kernel_id == "k-42"
        assert agent._turn_count == 3
        assert len(agent.chat_history) == 1


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


class TestTeardown:
    async def test_teardown_clears_state(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        [e async for e in adapter.execute(agent, user_input)]
        assert len(agent.chat_history) > 0
        await adapter.teardown(agent)
        assert agent.chat_history == []
        assert agent._turn_count == 0


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    async def test_execute_returns_async_iterator(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        result = adapter.execute(agent, user_input)
        assert hasattr(result, "__aiter__")
        events = [e async for e in result]
        assert len(events) > 0

    async def test_event_stream_order(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]
        types = [e.type for e in events]
        assert types[0] == AgentEventType.THINKING
        assert types[-1] == AgentEventType.DONE
