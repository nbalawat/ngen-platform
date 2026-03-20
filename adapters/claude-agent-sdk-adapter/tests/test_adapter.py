"""Tests for Claude Agent SDK adapter.

All tests use real implementations — no mocks. The adapter uses placeholder
tool handlers so tests are deterministic without API keys.
"""

from __future__ import annotations

import pytest

from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    ModelRef,
    StateSnapshot,
    ToolSpec,
)

from ngen_claude_sdk.adapter import ClaudeAgentSDKAdapter


@pytest.fixture()
def adapter():
    return ClaudeAgentSDKAdapter()


@pytest.fixture()
def basic_spec():
    return AgentSpec(
        name="test-agent",
        description="A test Claude agent",
        framework="claude-agent-sdk",
        model=ModelRef(name="claude-sonnet-4-20250514"),
        system_prompt="You are a helpful assistant.",
    )


@pytest.fixture()
def spec_with_tools():
    return AgentSpec(
        name="tool-agent",
        description="An agent with tools",
        framework="claude-agent-sdk",
        model=ModelRef(name="claude-sonnet-4-20250514"),
        system_prompt="You are a research assistant.",
        tools=[
            ToolSpec(name="search", description="Search the knowledge base"),
            ToolSpec(name="calculator", description="Perform calculations"),
        ],
    )


@pytest.fixture()
def spec_with_decision_loop():
    return AgentSpec(
        name="bounded-agent",
        description="Agent with bounded turns",
        framework="claude-agent-sdk",
        model=ModelRef(name="claude-sonnet-4-20250514"),
        system_prompt="You are a careful agent.",
        tools=[ToolSpec(name="lookup", description="Look up data")],
        decision_loop={"max_turns": 3},
    )


@pytest.fixture()
def user_input():
    return AgentInput(
        messages=[{"role": "user", "content": "What is the weather today?"}],
    )


class TestAdapterProperties:
    def test_adapter_name(self, adapter):
        assert adapter.name == "claude-agent-sdk"

    async def test_create_agent(self, adapter, basic_spec):
        agent = await adapter.create_agent(basic_spec)
        assert agent.name == "test-agent"
        assert agent.system_prompt == "You are a helpful assistant."
        assert agent.agent_id is not None
        assert len(agent.tools) == 0

    async def test_create_agent_with_tools(self, adapter, spec_with_tools):
        agent = await adapter.create_agent(spec_with_tools)
        assert agent.name == "tool-agent"
        assert len(agent.tools) == 2
        assert len(agent.tool_definitions) == 2
        assert agent.tool_definitions[0]["name"] == "search"
        assert agent.tool_definitions[1]["name"] == "calculator"

    async def test_create_agent_with_decision_loop(self, adapter, spec_with_decision_loop):
        agent = await adapter.create_agent(spec_with_decision_loop)
        assert agent.max_turns == 3


class TestBasicExecution:
    async def test_execute_without_tools(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, user_input)]

        event_types = [e.type for e in events]
        assert AgentEventType.THINKING in event_types
        assert AgentEventType.RESPONSE in event_types
        assert AgentEventType.DONE in event_types
        assert AgentEventType.COST_CHECKPOINT in event_types

        # No tool calls for agents without tools
        assert AgentEventType.TOOL_CALL_START not in event_types

    async def test_response_contains_input(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, user_input)]

        response_events = [e for e in events if e.type == AgentEventType.RESPONSE]
        assert len(response_events) == 1
        assert "What is the weather today?" in response_events[0].data["text"]

    async def test_all_events_have_agent_name(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, user_input)]

        for event in events:
            assert event.agent_name == "test-agent"

    async def test_all_events_have_timestamp(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, user_input)]

        for event in events:
            assert event.timestamp is not None
            assert event.timestamp > 0


class TestToolExecution:
    async def test_tool_call_events(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]

        tool_starts = [e for e in events if e.type == AgentEventType.TOOL_CALL_START]
        tool_ends = [e for e in events if e.type == AgentEventType.TOOL_CALL_END]

        # Both tools should be called
        assert len(tool_starts) == 2
        assert len(tool_ends) == 2

        # Verify tool names
        assert tool_starts[0].data["tool"] == "search"
        assert tool_starts[1].data["tool"] == "calculator"

    async def test_tool_call_has_id(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]

        tool_starts = [e for e in events if e.type == AgentEventType.TOOL_CALL_START]
        for ts in tool_starts:
            assert "tool_call_id" in ts.data
            assert len(ts.data["tool_call_id"]) > 0

    async def test_tool_result_in_end_event(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]

        tool_ends = [e for e in events if e.type == AgentEventType.TOOL_CALL_END]
        for te in tool_ends:
            assert "result" in te.data
            assert "executed" in te.data["result"]

    async def test_tool_names_in_response(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]

        response = [e for e in events if e.type == AgentEventType.RESPONSE][0]
        assert "search" in response.data["text"]
        assert "calculator" in response.data["text"]

    async def test_cost_checkpoint(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]

        cost_events = [e for e in events if e.type == AgentEventType.COST_CHECKPOINT]
        assert len(cost_events) == 1
        assert cost_events[0].data["tools_called"] == 2


class TestConversationHistory:
    async def test_messages_appended_after_execution(
        self, adapter, spec_with_tools, user_input
    ):
        agent = await adapter.create_agent(spec_with_tools)
        _ = [e async for e in adapter.execute(agent, user_input)]

        # Messages should include original + tool exchanges + final response
        assert len(agent.messages) > 1
        # Last message should be assistant response
        assert agent.messages[-1]["role"] == "assistant"

    async def test_multiple_roles_in_input(self, adapter, basic_spec):
        multi_turn = AgentInput(
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "What can you do?"},
            ],
        )
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, multi_turn)]

        response = [e for e in events if e.type == AgentEventType.RESPONSE][0]
        assert "What can you do?" in response.data["text"]


class TestCheckpointRestore:
    async def test_checkpoint_captures_state(
        self, adapter, spec_with_tools, user_input
    ):
        agent = await adapter.create_agent(spec_with_tools)
        _ = [e async for e in adapter.execute(agent, user_input)]

        snapshot = await adapter.checkpoint(agent)
        assert snapshot.agent_name == "tool-agent"
        assert snapshot.version == 1
        assert "messages" in snapshot.state
        assert "system_prompt" in snapshot.state
        assert snapshot.state["turn_count"] == 2

    async def test_restore_recovers_state(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        _ = [e async for e in adapter.execute(agent, user_input)]

        snapshot = await adapter.checkpoint(agent)

        # Create a fresh agent and restore
        agent2 = await adapter.create_agent(spec_with_tools)
        assert len(agent2.messages) == 0

        await adapter.restore(agent2, snapshot)
        assert len(agent2.messages) == len(agent.messages)
        assert agent2.system_prompt == agent.system_prompt
        assert agent2._turn_count == agent._turn_count

    async def test_restore_from_raw_snapshot(self, adapter, basic_spec):
        agent = await adapter.create_agent(basic_spec)

        raw_snapshot = StateSnapshot(
            agent_name="test-agent",
            state={
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi!"},
                ],
                "system_prompt": "Custom prompt",
                "turn_count": 5,
            },
        )

        await adapter.restore(agent, raw_snapshot)
        assert len(agent.messages) == 2
        assert agent.system_prompt == "Custom prompt"
        assert agent._turn_count == 5


class TestTeardown:
    async def test_teardown_clears_state(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        _ = [e async for e in adapter.execute(agent, user_input)]

        assert len(agent.messages) > 0
        assert agent._turn_count > 0

        await adapter.teardown(agent)
        assert len(agent.messages) == 0
        assert agent._turn_count == 0


class TestProtocolCompliance:
    """Verify the adapter satisfies the FrameworkAdapter protocol."""

    async def test_implements_protocol(self, adapter):
        from ngen_framework_core.protocols import FrameworkAdapter

        assert isinstance(adapter, FrameworkAdapter)

    async def test_execute_returns_async_iterator(
        self, adapter, basic_spec, user_input
    ):
        agent = await adapter.create_agent(basic_spec)
        result = adapter.execute(agent, user_input)
        # Should be an async iterator
        assert hasattr(result, "__aiter__")
        assert hasattr(result, "__anext__")
        # Consume it
        events = [e async for e in result]
        assert all(isinstance(e, AgentEvent) for e in events)

    async def test_event_stream_order(self, adapter, spec_with_tools, user_input):
        """Events should follow: THINKING → TOOL_CALL_START/END → COST → RESPONSE → DONE."""
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]

        types = [e.type for e in events]
        assert types[0] == AgentEventType.THINKING
        assert types[-1] == AgentEventType.DONE
        assert types[-2] == AgentEventType.RESPONSE
        assert types[-3] == AgentEventType.COST_CHECKPOINT
