"""Tests for CrewAI adapter.

All tests use real implementations — no mocks.
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

from ngen_crewai.adapter import CrewAIAdapter


@pytest.fixture()
def adapter():
    return CrewAIAdapter()


@pytest.fixture()
def researcher_spec():
    return AgentSpec(
        name="senior-researcher",
        description="An experienced research analyst with expertise in data analysis",
        framework="crewai",
        model=ModelRef(name="claude-sonnet-4-20250514"),
        system_prompt="Analyze data and produce insights for the team.",
        tools=[
            ToolSpec(name="search-papers", description="Search academic papers"),
            ToolSpec(name="summarize", description="Summarize documents"),
        ],
    )


@pytest.fixture()
def writer_spec():
    return AgentSpec(
        name="content-writer",
        description="A skilled writer who crafts compelling narratives",
        framework="crewai",
        model=ModelRef(name="claude-sonnet-4-20250514"),
        system_prompt="Write clear, engaging content based on research findings.",
    )


@pytest.fixture()
def user_input():
    return AgentInput(
        messages=[{"role": "user", "content": "Analyze Q4 revenue trends"}],
    )


class TestAdapterProperties:
    def test_adapter_name(self, adapter):
        assert adapter.name == "crewai"

    async def test_create_agent(self, adapter, researcher_spec):
        agent = await adapter.create_agent(researcher_spec)
        assert agent.name == "senior-researcher"
        assert agent.role.role == "Senior Researcher"
        assert agent.role.goal == "Analyze data and produce insights for the team."
        assert agent.role.backstory == "An experienced research analyst with expertise in data analysis"

    async def test_create_agent_without_tools(self, adapter, writer_spec):
        agent = await adapter.create_agent(writer_spec)
        assert agent.name == "content-writer"
        assert len(agent.tools) == 0
        assert agent.role.role == "Content Writer"

    async def test_decision_loop_bounds(self, adapter):
        spec = AgentSpec(
            name="bounded-agent",
            description="Agent with limits",
            framework="crewai",
            model=ModelRef(name="test"),
            system_prompt="test",
            decision_loop={"max_turns": 5},
        )
        agent = await adapter.create_agent(spec)
        assert agent.max_turns == 5


class TestExecution:
    async def test_execute_without_tools(self, adapter, writer_spec, user_input):
        agent = await adapter.create_agent(writer_spec)
        events = [e async for e in adapter.execute(agent, user_input)]

        types = [e.type for e in events]
        assert AgentEventType.THINKING in types
        assert AgentEventType.RESPONSE in types
        assert AgentEventType.DONE in types
        assert AgentEventType.TOOL_CALL_START not in types

    async def test_execute_with_tools(self, adapter, researcher_spec, user_input):
        agent = await adapter.create_agent(researcher_spec)
        events = [e async for e in adapter.execute(agent, user_input)]

        tool_starts = [e for e in events if e.type == AgentEventType.TOOL_CALL_START]
        tool_ends = [e for e in events if e.type == AgentEventType.TOOL_CALL_END]
        assert len(tool_starts) == 2
        assert len(tool_ends) == 2
        assert tool_starts[0].data["tool"] == "search-papers"
        assert tool_starts[1].data["tool"] == "summarize"

    async def test_response_includes_role(self, adapter, researcher_spec, user_input):
        agent = await adapter.create_agent(researcher_spec)
        events = [e async for e in adapter.execute(agent, user_input)]

        response = [e for e in events if e.type == AgentEventType.RESPONSE][0]
        assert "Senior Researcher" in response.data["text"]
        assert "role" in response.data
        assert "task_id" in response.data

    async def test_response_contains_input(self, adapter, researcher_spec, user_input):
        agent = await adapter.create_agent(researcher_spec)
        events = [e async for e in adapter.execute(agent, user_input)]

        response = [e for e in events if e.type == AgentEventType.RESPONSE][0]
        assert "Q4 revenue trends" in response.data["text"]

    async def test_thinking_includes_role(self, adapter, researcher_spec, user_input):
        agent = await adapter.create_agent(researcher_spec)
        events = [e async for e in adapter.execute(agent, user_input)]

        thinking = [e for e in events if e.type == AgentEventType.THINKING][0]
        assert "Senior Researcher" in thinking.data["text"]
        assert thinking.data["role"] == "Senior Researcher"

    async def test_all_events_have_agent_name(self, adapter, researcher_spec, user_input):
        agent = await adapter.create_agent(researcher_spec)
        events = [e async for e in adapter.execute(agent, user_input)]
        for event in events:
            assert event.agent_name == "senior-researcher"

    async def test_all_events_have_timestamp(self, adapter, researcher_spec, user_input):
        agent = await adapter.create_agent(researcher_spec)
        events = [e async for e in adapter.execute(agent, user_input)]
        for event in events:
            assert event.timestamp is not None
            assert event.timestamp > 0

    async def test_cost_checkpoint(self, adapter, researcher_spec, user_input):
        agent = await adapter.create_agent(researcher_spec)
        events = [e async for e in adapter.execute(agent, user_input)]

        cost = [e for e in events if e.type == AgentEventType.COST_CHECKPOINT][0]
        assert cost.data["tools_called"] == 2
        assert "task_id" in cost.data

    async def test_event_stream_order(self, adapter, researcher_spec, user_input):
        agent = await adapter.create_agent(researcher_spec)
        events = [e async for e in adapter.execute(agent, user_input)]

        types = [e.type for e in events]
        assert types[0] == AgentEventType.THINKING
        assert types[-1] == AgentEventType.DONE
        assert types[-2] == AgentEventType.RESPONSE
        assert types[-3] == AgentEventType.COST_CHECKPOINT


class TestTaskTracking:
    async def test_tasks_recorded(self, adapter, researcher_spec, user_input):
        agent = await adapter.create_agent(researcher_spec)
        _ = [e async for e in adapter.execute(agent, user_input)]

        assert len(agent.tasks) == 1
        assert agent.tasks[0].description == "Analyze Q4 revenue trends"
        assert agent.tasks[0].result is not None

    async def test_multiple_executions_accumulate_tasks(
        self, adapter, writer_spec
    ):
        agent = await adapter.create_agent(writer_spec)

        input1 = AgentInput(messages=[{"role": "user", "content": "Write intro"}])
        input2 = AgentInput(messages=[{"role": "user", "content": "Write conclusion"}])

        _ = [e async for e in adapter.execute(agent, input1)]
        _ = [e async for e in adapter.execute(agent, input2)]

        assert len(agent.tasks) == 2
        assert agent.tasks[0].description == "Write intro"
        assert agent.tasks[1].description == "Write conclusion"


class TestCheckpointRestore:
    async def test_checkpoint_captures_role(self, adapter, researcher_spec, user_input):
        agent = await adapter.create_agent(researcher_spec)
        _ = [e async for e in adapter.execute(agent, user_input)]

        snapshot = await adapter.checkpoint(agent)
        assert snapshot.state["role"]["role"] == "Senior Researcher"
        assert snapshot.state["role"]["goal"] == "Analyze data and produce insights for the team."

    async def test_checkpoint_captures_tasks(self, adapter, researcher_spec, user_input):
        agent = await adapter.create_agent(researcher_spec)
        _ = [e async for e in adapter.execute(agent, user_input)]

        snapshot = await adapter.checkpoint(agent)
        assert len(snapshot.state["tasks"]) == 1
        assert snapshot.state["tasks"][0]["result"] is not None

    async def test_restore_recovers_state(self, adapter, researcher_spec, user_input):
        agent = await adapter.create_agent(researcher_spec)
        _ = [e async for e in adapter.execute(agent, user_input)]

        snapshot = await adapter.checkpoint(agent)

        agent2 = await adapter.create_agent(researcher_spec)
        await adapter.restore(agent2, snapshot)

        assert agent2.role.role == agent.role.role
        assert len(agent2.tasks) == len(agent.tasks)
        assert agent2._turn_count == agent._turn_count

    async def test_restore_from_raw_snapshot(self, adapter, writer_spec):
        agent = await adapter.create_agent(writer_spec)

        snapshot = StateSnapshot(
            agent_name="content-writer",
            state={
                "messages": [{"role": "user", "content": "Hello"}],
                "role": {"role": "Editor", "goal": "Edit content", "backstory": "Expert editor"},
                "tasks": [
                    {"id": "t1", "description": "Edit draft", "expected_output": "Clean draft", "result": "Done"},
                ],
                "turn_count": 3,
            },
        )

        await adapter.restore(agent, snapshot)
        assert agent.role.role == "Editor"
        assert len(agent.tasks) == 1
        assert agent._turn_count == 3


class TestTeardown:
    async def test_teardown_clears_state(self, adapter, researcher_spec, user_input):
        agent = await adapter.create_agent(researcher_spec)
        _ = [e async for e in adapter.execute(agent, user_input)]

        assert len(agent.messages) > 0
        assert len(agent.tasks) > 0

        await adapter.teardown(agent)
        assert len(agent.messages) == 0
        assert len(agent.tasks) == 0
        assert agent._turn_count == 0


class TestProtocolCompliance:
    async def test_implements_protocol(self, adapter):
        from ngen_framework_core.protocols import FrameworkAdapter
        assert isinstance(adapter, FrameworkAdapter)

    async def test_execute_returns_async_iterator(self, adapter, writer_spec, user_input):
        agent = await adapter.create_agent(writer_spec)
        result = adapter.execute(agent, user_input)
        assert hasattr(result, "__aiter__")
        assert hasattr(result, "__anext__")
        events = [e async for e in result]
        assert all(isinstance(e, AgentEvent) for e in events)
