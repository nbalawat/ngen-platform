"""Tests for the LangGraph framework adapter."""

from __future__ import annotations

import pytest
from langgraph_adapter import LangGraphAdapter
from ngen_framework_core.protocols import (
    AgentEventType,
    AgentInput,
    AgentSpec,
    FrameworkAdapter,
    ModelRef,
    ToolSpec,
)
from ngen_framework_core.registry import AdapterRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter() -> LangGraphAdapter:
    return LangGraphAdapter()


@pytest.fixture
def simple_spec() -> AgentSpec:
    return AgentSpec(
        name="test-agent",
        description="A test agent",
        framework="langgraph",
        model=ModelRef(name="claude-opus-4-6"),
        system_prompt="You are a helpful test assistant.",
    )


@pytest.fixture
def spec_with_tools() -> AgentSpec:
    return AgentSpec(
        name="tool-agent",
        description="Agent with tools",
        framework="langgraph",
        model=ModelRef(name="claude-opus-4-6"),
        system_prompt="You are a helpful assistant with tools.",
        tools=[
            ToolSpec(name="search", description="Search the knowledge base"),
            ToolSpec(name="calculate", description="Perform calculations"),
        ],
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_framework_adapter(self, adapter: LangGraphAdapter) -> None:
        assert isinstance(adapter, FrameworkAdapter)

    def test_adapter_name(self, adapter: LangGraphAdapter) -> None:
        assert adapter.name == "langgraph"

    def test_can_register_in_registry(self, adapter: LangGraphAdapter) -> None:
        registry = AdapterRegistry()
        registry.register(adapter)
        assert registry.get("langgraph") is adapter


# ---------------------------------------------------------------------------
# Agent creation
# ---------------------------------------------------------------------------


class TestCreateAgent:
    async def test_creates_agent(self, adapter: LangGraphAdapter, simple_spec: AgentSpec) -> None:
        agent = await adapter.create_agent(simple_spec)
        assert agent.name == "test-agent"
        assert agent.spec is simple_spec
        assert agent.agent_id  # UUID assigned

    async def test_creates_agent_with_tools(
        self, adapter: LangGraphAdapter, spec_with_tools: AgentSpec
    ) -> None:
        agent = await adapter.create_agent(spec_with_tools)
        assert len(agent.tools) == 2
        tool_names = [t.name for t in agent.tools]
        assert "search" in tool_names
        assert "calculate" in tool_names

    async def test_agent_has_compiled_graph(
        self, adapter: LangGraphAdapter, simple_spec: AgentSpec
    ) -> None:
        agent = await adapter.create_agent(simple_spec)
        assert agent.graph is not None


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class TestExecute:
    async def test_execute_produces_events(
        self, adapter: LangGraphAdapter, simple_spec: AgentSpec
    ) -> None:
        agent = await adapter.create_agent(simple_spec)
        input_data = AgentInput(messages=[{"role": "user", "content": "Hello!"}])

        events = []
        async for event in adapter.execute(agent, input_data):
            events.append(event)

        assert len(events) >= 2
        # First event: starting message
        assert events[0].type == AgentEventType.TEXT_DELTA
        assert "Starting" in events[0].data["text"]
        # Last event: DONE
        assert events[-1].type == AgentEventType.DONE
        # All events tagged with agent name
        for event in events:
            assert event.agent_name == "test-agent"
            assert event.timestamp is not None

    async def test_execute_includes_response(
        self, adapter: LangGraphAdapter, simple_spec: AgentSpec
    ) -> None:
        agent = await adapter.create_agent(simple_spec)
        input_data = AgentInput(messages=[{"role": "user", "content": "What is 2+2?"}])

        text_events = []
        async for event in adapter.execute(agent, input_data):
            if event.type == AgentEventType.TEXT_DELTA:
                text_events.append(event)

        # Should have at least a starting event and a response event
        assert len(text_events) >= 2
        # Response should reference the input
        response_text = text_events[-1].data["text"]
        assert "What is 2+2?" in response_text

    async def test_execute_with_session_id(
        self, adapter: LangGraphAdapter, simple_spec: AgentSpec
    ) -> None:
        agent = await adapter.create_agent(simple_spec)
        input_data = AgentInput(
            messages=[{"role": "user", "content": "Test"}],
            session_id="sess-123",
        )

        events = []
        async for event in adapter.execute(agent, input_data):
            events.append(event)

        assert events[-1].type == AgentEventType.DONE


# ---------------------------------------------------------------------------
# Checkpoint & restore
# ---------------------------------------------------------------------------


class TestCheckpointRestore:
    async def test_checkpoint_returns_snapshot(
        self, adapter: LangGraphAdapter, simple_spec: AgentSpec
    ) -> None:
        agent = await adapter.create_agent(simple_spec)
        input_data = AgentInput(messages=[{"role": "user", "content": "Remember this"}])

        async for _ in adapter.execute(agent, input_data):
            pass

        snapshot = await adapter.checkpoint(agent)
        assert snapshot.agent_name == "test-agent"
        assert snapshot.version == 1
        assert "messages" in snapshot.state
        assert len(snapshot.state["messages"]) > 0

    async def test_restore_recovers_state(
        self, adapter: LangGraphAdapter, simple_spec: AgentSpec
    ) -> None:
        agent = await adapter.create_agent(simple_spec)
        input_data = AgentInput(messages=[{"role": "user", "content": "State test"}])

        async for _ in adapter.execute(agent, input_data):
            pass

        snapshot = await adapter.checkpoint(agent)

        # Create a new agent and restore state into it
        new_agent = await adapter.create_agent(simple_spec)
        await adapter.restore(new_agent, snapshot)

        # Verify state was restored
        new_snapshot = await adapter.checkpoint(new_agent)
        assert len(new_snapshot.state["messages"]) == len(snapshot.state["messages"])

    async def test_checkpoint_empty_state(
        self, adapter: LangGraphAdapter, simple_spec: AgentSpec
    ) -> None:
        agent = await adapter.create_agent(simple_spec)
        snapshot = await adapter.checkpoint(agent)
        assert snapshot.state["messages"] == []


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


class TestTeardown:
    async def test_teardown_clears_state(
        self, adapter: LangGraphAdapter, simple_spec: AgentSpec
    ) -> None:
        agent = await adapter.create_agent(simple_spec)
        input_data = AgentInput(messages=[{"role": "user", "content": "Hi"}])

        async for _ in adapter.execute(agent, input_data):
            pass

        assert agent._state  # Has state after execution
        await adapter.teardown(agent)
        assert agent._state == {}  # State cleared
