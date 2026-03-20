"""Tests for Google ADK adapter — session-based function-calling pattern."""

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
from ngen_adk.adapter import ADKAgent, GoogleADKAdapter


@pytest.fixture()
def adapter() -> GoogleADKAdapter:
    return GoogleADKAdapter()


@pytest.fixture()
def basic_spec() -> AgentSpec:
    return AgentSpec(
        name="search-agent",
        description="Searches knowledge base",
        framework="google-adk",
        model=ModelRef(name="gemini-pro"),
        system_prompt="You search documents and answer questions.",
    )


@pytest.fixture()
def spec_with_tools() -> AgentSpec:
    return AgentSpec(
        name="tool-agent",
        description="Agent with tools",
        framework="google-adk",
        model=ModelRef(name="gemini-pro"),
        system_prompt="Use tools to help users.",
        tools=[
            ToolSpec(name="search", description="Search documents"),
            ToolSpec(name="summarize", description="Summarize text"),
        ],
    )


@pytest.fixture()
def user_input() -> AgentInput:
    return AgentInput(
        messages=[{"role": "user", "content": "Find info about quantum computing"}],
    )


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestAdapterProperties:
    def test_name(self, adapter):
        assert adapter.name == "google-adk"

    async def test_create_agent(self, adapter, basic_spec):
        agent = await adapter.create_agent(basic_spec)
        assert isinstance(agent, ADKAgent)
        assert agent.name == "search-agent"
        assert agent.instructions == "You search documents and answer questions."
        assert agent.session.session_id  # Has a session

    async def test_create_agent_with_tools(self, adapter, spec_with_tools):
        agent = await adapter.create_agent(spec_with_tools)
        assert len(agent.tools) == 2
        assert agent.tools[0].name == "search"

    async def test_create_agent_with_sub_agents(self, adapter):
        spec = AgentSpec(
            name="orchestrator",
            description="Orchestrator agent",
            framework="google-adk",
            model=ModelRef(name="gemini-pro"),
            system_prompt="Orchestrate sub-agents.",
            metadata={"sub_agents": ["worker-a", "worker-b"]},
        )
        agent = await adapter.create_agent(spec)
        assert agent.sub_agents == ["worker-a", "worker-b"]


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
        assert "quantum computing" in response.data["text"]

    async def test_all_events_have_agent_name(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, user_input)]
        assert all(e.agent_name == "search-agent" for e in events)

    async def test_all_events_have_timestamp(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, user_input)]
        assert all(e.timestamp > 0 for e in events)

    async def test_thinking_includes_instructions(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, user_input)]
        thinking = next(e for e in events if e.type == AgentEventType.THINKING)
        assert "instructions" in thinking.data


class TestToolExecution:
    async def test_tool_call_events(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]

        starts = [e for e in events if e.type == AgentEventType.TOOL_CALL_START]
        ends = [e for e in events if e.type == AgentEventType.TOOL_CALL_END]
        assert len(starts) == 2
        assert len(ends) == 2

    async def test_tool_call_has_id(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]
        start = next(e for e in events if e.type == AgentEventType.TOOL_CALL_START)
        assert "tool_call_id" in start.data

    async def test_tool_names_in_response(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]
        response = next(e for e in events if e.type == AgentEventType.RESPONSE)
        assert "search" in response.data["text"]

    async def test_cost_checkpoint(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]
        cost = next(e for e in events if e.type == AgentEventType.COST_CHECKPOINT)
        assert cost.data["turns"] == 2
        assert cost.data["tools_called"] == 2


# ---------------------------------------------------------------------------
# Session / conversation
# ---------------------------------------------------------------------------


class TestSessionHistory:
    async def test_session_updated_after_execution(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        [e async for e in adapter.execute(agent, user_input)]
        # Session should contain user message + assistant response
        assert len(agent.session.history) >= 2
        assert agent.session.history[0]["role"] == "user"
        assert agent.session.history[-1]["role"] == "assistant"

    async def test_session_id_in_events(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        events = [e async for e in adapter.execute(agent, user_input)]
        done = next(e for e in events if e.type == AgentEventType.DONE)
        assert done.data["session_id"] == agent.session.session_id


# ---------------------------------------------------------------------------
# Checkpoint / restore
# ---------------------------------------------------------------------------


class TestCheckpointRestore:
    async def test_checkpoint_captures_state(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        [e async for e in adapter.execute(agent, user_input)]
        snapshot = await adapter.checkpoint(agent)
        assert snapshot.agent_name == "search-agent"
        assert "session" in snapshot.state
        assert len(snapshot.state["session"]["history"]) >= 2

    async def test_restore_recovers_state(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        [e async for e in adapter.execute(agent, user_input)]
        snapshot = await adapter.checkpoint(agent)

        # Create fresh agent and restore
        agent2 = await adapter.create_agent(basic_spec)
        assert len(agent2.session.history) == 0
        await adapter.restore(agent2, snapshot)
        assert len(agent2.session.history) >= 2
        assert agent2.session.session_id == agent.session.session_id

    async def test_restore_from_raw_snapshot(self, adapter, basic_spec):
        agent = await adapter.create_agent(basic_spec)
        raw = StateSnapshot(
            agent_name="search-agent",
            state={
                "session": {
                    "session_id": "ses-123",
                    "history": [{"role": "user", "content": "hi"}],
                    "metadata": {"key": "val"},
                },
                "turn_count": 5,
            },
        )
        await adapter.restore(agent, raw)
        assert agent.session.session_id == "ses-123"
        assert agent._turn_count == 5
        assert len(agent.session.history) == 1


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


class TestTeardown:
    async def test_teardown_clears_state(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        [e async for e in adapter.execute(agent, user_input)]
        assert len(agent.session.history) > 0
        await adapter.teardown(agent)
        assert agent.session.history == []
        assert agent._turn_count == 0


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    async def test_execute_returns_async_iterator(self, adapter, basic_spec, user_input):
        agent = await adapter.create_agent(basic_spec)
        result = adapter.execute(agent, user_input)
        assert hasattr(result, "__aiter__")
        assert hasattr(result, "__anext__")
        events = [e async for e in result]
        assert len(events) > 0

    async def test_event_stream_order(self, adapter, spec_with_tools, user_input):
        agent = await adapter.create_agent(spec_with_tools)
        events = [e async for e in adapter.execute(agent, user_input)]
        types = [e.type for e in events]
        # THINKING should come first, DONE should come last
        assert types[0] == AgentEventType.THINKING
        assert types[-1] == AgentEventType.DONE
