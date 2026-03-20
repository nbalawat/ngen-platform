"""End-to-end tests for the AgentExecutor.

Exercises the full flow: spec → adapter lookup → create → execute → checkpoint
→ restore → teardown.
"""

from __future__ import annotations

import pytest
from langgraph_adapter import LangGraphAdapter
from ngen_framework_core.executor import AgentExecutor, ToolExecutor
from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    ModelRef,
    ToolComponentSpec,
    ToolSpec,
)
from ngen_framework_core.registry import AdapterRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> AdapterRegistry:
    reg = AdapterRegistry()
    reg.register(LangGraphAdapter())
    return reg


@pytest.fixture
def executor(registry: AdapterRegistry) -> AgentExecutor:
    return AgentExecutor(registry=registry)


@pytest.fixture
def agent_spec() -> AgentSpec:
    return AgentSpec(
        name="e2e-agent",
        description="End-to-end test agent",
        framework="langgraph",
        model=ModelRef(name="claude-opus-4-6"),
        system_prompt="You are a helpful assistant.",
        tools=[
            ToolSpec(name="search-kb", description="Search the knowledge base"),
        ],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEndToEndExecution:
    """Full lifecycle: create → execute → checkpoint → restore → teardown."""

    async def test_full_lifecycle(self, executor: AgentExecutor, agent_spec: AgentSpec) -> None:
        # 1. Create agent
        agent = await executor.create(agent_spec)
        assert agent is not None
        assert "e2e-agent" in executor.agent_names

        # 2. Execute agent
        input_data = AgentInput(messages=[{"role": "user", "content": "Hello, agent!"}])
        events = []
        async for event in executor.execute("e2e-agent", input_data):
            events.append(event)

        # Verify events structure
        assert len(events) >= 2
        assert events[-1].type == AgentEventType.DONE
        text_events = [e for e in events if e.type == AgentEventType.TEXT_DELTA]
        assert len(text_events) >= 1

        # 3. Checkpoint
        snapshot = await executor.checkpoint("e2e-agent")
        assert snapshot.agent_name == "e2e-agent"
        assert len(snapshot.state["messages"]) > 0

        # 4. Teardown
        await executor.teardown("e2e-agent")
        assert "e2e-agent" not in executor.agent_names

    async def test_create_and_execute_multiple_agents(self, executor: AgentExecutor) -> None:
        spec_a = AgentSpec(
            name="agent-a",
            description="Agent A",
            framework="langgraph",
            model=ModelRef(name="test-model"),
            system_prompt="You are agent A.",
        )
        spec_b = AgentSpec(
            name="agent-b",
            description="Agent B",
            framework="langgraph",
            model=ModelRef(name="test-model"),
            system_prompt="You are agent B.",
        )

        await executor.create(spec_a)
        await executor.create(spec_b)
        assert sorted(executor.agent_names) == ["agent-a", "agent-b"]

        # Execute both
        for name in ["agent-a", "agent-b"]:
            events = []
            async for event in executor.execute(
                name, AgentInput(messages=[{"role": "user", "content": "Hi"}])
            ):
                events.append(event)
            assert events[-1].type == AgentEventType.DONE

        await executor.teardown_all()
        assert executor.agent_names == []

    async def test_checkpoint_restore_continuity(
        self, executor: AgentExecutor, agent_spec: AgentSpec
    ) -> None:
        """Verify that checkpoint → restore preserves state."""
        await executor.create(agent_spec)

        # Execute first interaction
        input1 = AgentInput(messages=[{"role": "user", "content": "Remember: code is ALPHA"}])
        async for _ in executor.execute("e2e-agent", input1):
            pass

        snapshot = await executor.checkpoint("e2e-agent")
        original_msg_count = len(snapshot.state["messages"])

        # Restore into same agent
        await executor.restore("e2e-agent", snapshot)
        restored_snapshot = await executor.checkpoint("e2e-agent")
        assert len(restored_snapshot.state["messages"]) == original_msg_count

        await executor.teardown("e2e-agent")

    async def test_execute_unknown_agent_raises(self, executor: AgentExecutor) -> None:
        with pytest.raises(KeyError, match="not found"):
            async for _ in executor.execute(
                "ghost", AgentInput(messages=[{"role": "user", "content": "Hi"}])
            ):
                pass

    async def test_create_unknown_framework_raises(self, executor: AgentExecutor) -> None:
        bad_spec = AgentSpec(
            name="bad",
            description="Bad agent",
            framework="nonexistent-framework",
            model=ModelRef(name="model"),
            system_prompt="nope",
        )
        with pytest.raises(KeyError, match="nonexistent-framework"):
            await executor.create(bad_spec)

    async def test_teardown_all_empty(self, executor: AgentExecutor) -> None:
        await executor.teardown_all()  # should not raise
        assert executor.agent_names == []


# ---------------------------------------------------------------------------
# Interceptor tests
# ---------------------------------------------------------------------------


class _PassthroughInterceptor:
    async def intercept(self, event: AgentEvent) -> AgentEvent | None:
        return event


class _HaltOnDoneInterceptor:
    """Halts the stream when a DONE event is seen (before it reaches the consumer)."""

    async def intercept(self, event: AgentEvent) -> AgentEvent | None:
        if event.type == AgentEventType.DONE:
            return None
        return event


class _TaggingInterceptor:
    """Adds a tag to every event."""

    async def intercept(self, event: AgentEvent) -> AgentEvent | None:
        event.data["tagged"] = True
        return event


class TestExecutorInterceptors:
    async def test_passthrough_interceptor(
        self, registry: AdapterRegistry, agent_spec: AgentSpec
    ) -> None:
        executor = AgentExecutor(registry=registry, interceptors=[_PassthroughInterceptor()])
        await executor.create(agent_spec)

        events = []
        async for event in executor.execute(
            "e2e-agent", AgentInput(messages=[{"role": "user", "content": "Hi"}])
        ):
            events.append(event)

        assert len(events) >= 2
        assert events[-1].type == AgentEventType.DONE
        await executor.teardown_all()

    async def test_halting_interceptor(
        self, registry: AdapterRegistry, agent_spec: AgentSpec
    ) -> None:
        executor = AgentExecutor(registry=registry, interceptors=[_HaltOnDoneInterceptor()])
        await executor.create(agent_spec)

        events = []
        async for event in executor.execute(
            "e2e-agent", AgentInput(messages=[{"role": "user", "content": "Hi"}])
        ):
            events.append(event)

        # DONE event should have been halted
        assert all(e.type != AgentEventType.DONE for e in events)
        await executor.teardown_all()

    async def test_tagging_interceptor(
        self, registry: AdapterRegistry, agent_spec: AgentSpec
    ) -> None:
        executor = AgentExecutor(registry=registry, interceptors=[_TaggingInterceptor()])
        await executor.create(agent_spec)

        events = []
        async for event in executor.execute(
            "e2e-agent", AgentInput(messages=[{"role": "user", "content": "Hi"}])
        ):
            events.append(event)

        assert all(e.data.get("tagged") is True for e in events)
        await executor.teardown_all()

    async def test_add_interceptor_at_runtime(
        self, registry: AdapterRegistry, agent_spec: AgentSpec
    ) -> None:
        executor = AgentExecutor(registry=registry)
        executor.add_interceptor(_TaggingInterceptor())
        await executor.create(agent_spec)

        events = []
        async for event in executor.execute(
            "e2e-agent", AgentInput(messages=[{"role": "user", "content": "Hi"}])
        ):
            events.append(event)

        assert all(e.data.get("tagged") is True for e in events)
        await executor.teardown_all()


# ---------------------------------------------------------------------------
# ToolExecutor tests
# ---------------------------------------------------------------------------


class TestToolExecutor:
    async def test_sync_handler(self) -> None:
        spec = ToolComponentSpec(name="adder", description="Adds numbers")

        def add(data: dict) -> int:
            return data["a"] + data["b"]

        executor = ToolExecutor()
        result = await executor.execute(spec, {"a": 2, "b": 3}, handler_fn=add)
        assert result.type == AgentEventType.RESPONSE
        assert result.data["result"] == 5
        assert result.data["tool"] == "adder"

    async def test_async_handler(self) -> None:
        spec = ToolComponentSpec(name="greeter", description="Greets")

        async def greet(data: dict) -> str:
            return f"Hello, {data['name']}!"

        executor = ToolExecutor()
        result = await executor.execute(spec, {"name": "Alice"}, handler_fn=greet)
        assert result.type == AgentEventType.RESPONSE
        assert result.data["result"] == "Hello, Alice!"

    async def test_handler_error(self) -> None:
        spec = ToolComponentSpec(name="failing", description="Always fails")

        def fail(data: dict) -> None:
            raise RuntimeError("boom")

        executor = ToolExecutor()
        result = await executor.execute(spec, {}, handler_fn=fail)
        assert result.type == AgentEventType.ERROR
        assert "boom" in result.data["error"]

    async def test_no_handler_raises(self) -> None:
        spec = ToolComponentSpec(name="nohandler", description="No handler")
        executor = ToolExecutor()
        with pytest.raises(ValueError, match="No handler"):
            await executor.execute(spec, {})

    async def test_interceptor_on_tool_executor(self) -> None:
        spec = ToolComponentSpec(name="calc", description="Calculator")

        def double(data: dict) -> int:
            return data["x"] * 2

        executor = ToolExecutor(interceptors=[_TaggingInterceptor()])
        result = await executor.execute(spec, {"x": 5}, handler_fn=double)
        assert result.type == AgentEventType.RESPONSE
        assert result.data["result"] == 10
        assert result.data["tagged"] is True

    async def test_interceptor_halt_on_tool_executor(self) -> None:
        spec = ToolComponentSpec(name="calc", description="Calculator")

        class _AlwaysHalt:
            async def intercept(self, event: AgentEvent) -> AgentEvent | None:
                return None

        def identity(data: dict) -> dict:
            return data

        executor = ToolExecutor(interceptors=[_AlwaysHalt()])
        result = await executor.execute(spec, {"x": 1}, handler_fn=identity)
        assert result.type == AgentEventType.ERROR
        assert "Halted by interceptor" in result.data["error"]
