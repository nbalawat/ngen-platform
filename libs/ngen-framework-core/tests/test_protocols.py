"""Tests for core protocol classes and value objects."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Any

import pytest
from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    ComponentType,
    CostConfig,
    EscalationConfig,
    EvalConfig,
    EventInterceptor,
    FrameworkAdapter,
    GuardrailRef,
    MCPServerRef,
    MemoryConfig,
    ModelRef,
    SkillSpec,
    StateSnapshot,
    ToolComponentSpec,
    ToolSpec,
    WorkflowSpec,
)

# ---------------------------------------------------------------------------
# Value object tests
# ---------------------------------------------------------------------------


class TestModelRef:
    def test_create_minimal(self) -> None:
        ref = ModelRef(name="claude-opus-4-6")
        assert ref.name == "claude-opus-4-6"
        assert ref.fallback is None
        assert ref.parameters == {}

    def test_create_with_fallback(self) -> None:
        ref = ModelRef(name="claude-opus-4-6", fallback="claude-sonnet-4-6")
        assert ref.fallback == "claude-sonnet-4-6"

    def test_immutable(self) -> None:
        ref = ModelRef(name="claude-opus-4-6")
        with pytest.raises(AttributeError):
            ref.name = "other"  # type: ignore[misc]

    def test_serializable(self) -> None:
        ref = ModelRef(name="claude-opus-4-6", fallback="claude-sonnet-4-6")
        d = asdict(ref)
        assert d == {
            "name": "claude-opus-4-6",
            "fallback": "claude-sonnet-4-6",
            "parameters": {},
        }


class TestMCPServerRef:
    def test_create(self) -> None:
        ref = MCPServerRef(name="knowledge-base", version="1.0.0")
        assert ref.name == "knowledge-base"
        assert ref.version == "1.0.0"


class TestGuardrailRef:
    def test_create(self) -> None:
        ref = GuardrailRef(name="pii-redaction", config={"mode": "strict"})
        assert ref.name == "pii-redaction"
        assert ref.config == {"mode": "strict"}


class TestMemoryConfig:
    def test_defaults(self) -> None:
        config = MemoryConfig()
        assert config.short_term is True
        assert config.long_term is False
        assert config.vector_store is None
        assert config.ttl_seconds is None

    def test_custom(self) -> None:
        config = MemoryConfig(long_term=True, vector_store="pgvector", ttl_seconds=3600)
        assert config.long_term is True
        assert config.vector_store == "pgvector"


class TestToolSpec:
    def test_mcp_tool(self) -> None:
        tool = ToolSpec(
            name="search-kb",
            description="Search the knowledge base",
            mcp_server=MCPServerRef(name="knowledge-base"),
        )
        assert tool.name == "search-kb"
        assert tool.mcp_server is not None
        assert tool.mcp_server.name == "knowledge-base"
        assert tool.handler is None

    def test_handler_tool(self) -> None:
        tool = ToolSpec(
            name="custom-tool",
            description="A custom tool",
            handler="my_module.tools:my_handler",
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        )
        assert tool.handler == "my_module.tools:my_handler"
        assert "query" in tool.parameters["properties"]


class TestAgentSpec:
    def test_create_full(self) -> None:
        spec = AgentSpec(
            name="support-bot",
            description="Customer support agent",
            framework="langgraph",
            model=ModelRef(name="claude-opus-4-6"),
            system_prompt="You are a support agent.",
            tools=[
                ToolSpec(
                    name="search-kb",
                    description="Search KB",
                    mcp_server=MCPServerRef(name="kb"),
                ),
            ],
            guardrails=[GuardrailRef(name="pii-redaction")],
        )
        assert spec.name == "support-bot"
        assert spec.framework == "langgraph"
        assert len(spec.tools) == 1
        assert len(spec.guardrails) == 1

    def test_create_minimal(self) -> None:
        spec = AgentSpec(
            name="simple-bot",
            description="Simple",
            framework="claude-agent-sdk",
            model=ModelRef(name="claude-sonnet-4-6"),
            system_prompt="Hello",
        )
        assert spec.tools == []
        assert spec.guardrails == []

    def test_serializable(self) -> None:
        spec = AgentSpec(
            name="bot",
            description="d",
            framework="crewai",
            model=ModelRef(name="m"),
            system_prompt="p",
        )
        d = asdict(spec)
        assert d["name"] == "bot"
        assert d["framework"] == "crewai"
        assert isinstance(d["model"], dict)


class TestWorkflowSpec:
    def test_sequential(self) -> None:
        wf = WorkflowSpec(
            name="pipeline",
            description="Support pipeline",
            agents=["triage-bot", "support-bot", "feedback-bot"],
            topology="sequential",
        )
        assert len(wf.agents) == 3
        assert wf.topology == "sequential"

    def test_graph_with_edges(self) -> None:
        wf = WorkflowSpec(
            name="graph-wf",
            description="Graph workflow",
            agents=["a", "b", "c"],
            topology="graph",
            edges=[
                {"from": "a", "to": "b"},
                {"from": "b", "to": "c"},
            ],
        )
        assert len(wf.edges) == 2


# ---------------------------------------------------------------------------
# Agent execution type tests
# ---------------------------------------------------------------------------


class TestAgentInput:
    def test_create(self) -> None:
        inp = AgentInput(
            messages=[{"role": "user", "content": "Hello"}],
            session_id="sess-123",
        )
        assert len(inp.messages) == 1
        assert inp.session_id == "sess-123"


class TestAgentEvent:
    def test_text_delta(self) -> None:
        event = AgentEvent(
            type=AgentEventType.TEXT_DELTA,
            data={"text": "Hello"},
            agent_name="bot",
        )
        assert event.type == AgentEventType.TEXT_DELTA
        assert event.data["text"] == "Hello"

    def test_tool_call(self) -> None:
        event = AgentEvent(
            type=AgentEventType.TOOL_CALL_START,
            data={"tool": "search-kb", "input": {"query": "help"}},
        )
        assert event.type == AgentEventType.TOOL_CALL_START

    def test_all_event_types_exist(self) -> None:
        expected = {
            "TEXT_DELTA",
            "TOOL_CALL_START",
            "TOOL_CALL_END",
            "THINKING",
            "ERROR",
            "DONE",
            "STATE_CHECKPOINT",
            "RESPONSE",
            "ESCALATION",
            "GUARDRAIL_TRIGGER",
            "COST_CHECKPOINT",
            "MEMORY_WRITE",
            "MEMORY_EXPIRE",
            "MEMORY_SUMMARIZE",
        }
        actual = {e.name for e in AgentEventType}
        assert actual == expected


class TestStateSnapshot:
    def test_create(self) -> None:
        snapshot = StateSnapshot(
            agent_name="bot",
            state={"messages": [], "context": {}},
            version=1,
        )
        assert snapshot.agent_name == "bot"
        assert snapshot.version == 1


# ---------------------------------------------------------------------------
# FrameworkAdapter protocol tests
# ---------------------------------------------------------------------------


class MockAdapter:
    """A mock adapter that satisfies the FrameworkAdapter protocol."""

    @property
    def name(self) -> str:
        return "mock"

    async def create_agent(self, spec: AgentSpec) -> Any:
        return {"spec": spec}

    async def execute(
        self,
        agent: Any,
        input: AgentInput,
    ) -> AsyncIterator[AgentEvent]:
        yield AgentEvent(type=AgentEventType.TEXT_DELTA, data={"text": "mock response"})
        yield AgentEvent(type=AgentEventType.DONE)

    async def checkpoint(self, agent: Any) -> StateSnapshot:
        return StateSnapshot(agent_name="mock", state={})

    async def restore(self, agent: Any, snapshot: StateSnapshot) -> None:
        pass

    async def teardown(self, agent: Any) -> None:
        pass


class TestFrameworkAdapterProtocol:
    def test_mock_satisfies_protocol(self) -> None:
        adapter = MockAdapter()
        assert isinstance(adapter, FrameworkAdapter)

    def test_adapter_name(self) -> None:
        adapter = MockAdapter()
        assert adapter.name == "mock"

    @pytest.mark.asyncio
    async def test_create_and_execute(self) -> None:
        adapter = MockAdapter()
        spec = AgentSpec(
            name="test",
            description="test",
            framework="mock",
            model=ModelRef(name="test-model"),
            system_prompt="test",
        )
        agent = await adapter.create_agent(spec)
        assert agent is not None

        events: list[AgentEvent] = []
        async for event in adapter.execute(
            agent, AgentInput(messages=[{"role": "user", "content": "hi"}])
        ):
            events.append(event)

        assert len(events) == 2
        assert events[0].type == AgentEventType.TEXT_DELTA
        assert events[1].type == AgentEventType.DONE

    @pytest.mark.asyncio
    async def test_checkpoint_restore(self) -> None:
        adapter = MockAdapter()
        spec = AgentSpec(
            name="test",
            description="test",
            framework="mock",
            model=ModelRef(name="m"),
            system_prompt="p",
        )
        agent = await adapter.create_agent(spec)
        snapshot = await adapter.checkpoint(agent)
        assert isinstance(snapshot, StateSnapshot)

        await adapter.restore(agent, snapshot)  # Should not raise

    @pytest.mark.asyncio
    async def test_teardown(self) -> None:
        adapter = MockAdapter()
        agent = await adapter.create_agent(
            AgentSpec(
                name="t",
                description="t",
                framework="mock",
                model=ModelRef(name="m"),
                system_prompt="p",
            )
        )
        await adapter.teardown(agent)  # Should not raise

    def test_non_adapter_does_not_satisfy_protocol(self) -> None:
        class NotAnAdapter:
            pass

        assert not isinstance(NotAnAdapter(), FrameworkAdapter)


# ---------------------------------------------------------------------------
# RAPIDS component type tests
# ---------------------------------------------------------------------------


class TestComponentType:
    def test_all_values(self) -> None:
        assert {e.value for e in ComponentType} == {"tool", "skill", "agent"}

    def test_from_value(self) -> None:
        assert ComponentType("tool") == ComponentType.TOOL
        assert ComponentType("skill") == ComponentType.SKILL
        assert ComponentType("agent") == ComponentType.AGENT


class TestToolComponentSpec:
    def test_create_minimal(self) -> None:
        spec = ToolComponentSpec(name="calculator", description="Math tool")
        assert spec.name == "calculator"
        assert spec.input_schema == {}
        assert spec.output_schema == {}
        assert spec.handler is None
        assert spec.timeout_ms == 30_000
        assert spec.idempotent is False

    def test_create_full(self) -> None:
        spec = ToolComponentSpec(
            name="search",
            description="Search tool",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"results": {"type": "array"}}},
            handler="my_module:search_handler",
            mcp_server=MCPServerRef(name="search-server"),
            timeout_ms=5000,
            idempotent=True,
        )
        assert spec.handler == "my_module:search_handler"
        assert spec.mcp_server.name == "search-server"
        assert spec.timeout_ms == 5000
        assert spec.idempotent is True

    def test_serializable(self) -> None:
        spec = ToolComponentSpec(name="t", description="d")
        d = asdict(spec)
        assert d["name"] == "t"
        assert d["timeout_ms"] == 30_000


class TestEvalConfig:
    def test_defaults(self) -> None:
        config = EvalConfig()
        assert config.dimensions == []
        assert config.threshold == 0.8
        assert config.dataset_ref is None

    def test_custom(self) -> None:
        config = EvalConfig(
            dimensions=["accuracy", "latency"],
            threshold=0.9,
            dataset_ref="eval-dataset-v1",
        )
        assert len(config.dimensions) == 2
        assert config.threshold == 0.9


class TestCostConfig:
    def test_defaults(self) -> None:
        config = CostConfig()
        assert config.max_cost_per_invocation is None
        assert config.daily_budget is None
        assert config.alert_threshold == 0.8

    def test_custom(self) -> None:
        config = CostConfig(
            max_cost_per_invocation=0.50,
            daily_budget=100.0,
            alert_threshold=0.9,
        )
        assert config.max_cost_per_invocation == 0.50
        assert config.daily_budget == 100.0


class TestEscalationConfig:
    def test_defaults(self) -> None:
        config = EscalationConfig()
        assert config.target is None
        assert config.conditions == []
        assert config.timeout_seconds == 3600

    def test_custom(self) -> None:
        config = EscalationConfig(
            target="senior-agent",
            conditions=["confidence_below_threshold", "error_rate_high"],
            timeout_seconds=1800,
        )
        assert config.target == "senior-agent"
        assert len(config.conditions) == 2


class TestSkillSpec:
    def test_create_minimal(self) -> None:
        spec = SkillSpec(
            name="summarizer",
            description="Summarization skill",
            model=ModelRef(name="claude-opus-4-6"),
            system_prompt="Summarize the input text.",
        )
        assert spec.name == "summarizer"
        assert spec.tools == []
        assert spec.guardrails == []
        assert spec.eval_config.threshold == 0.8
        assert spec.cost.max_cost_per_invocation is None

    def test_create_full(self) -> None:
        spec = SkillSpec(
            name="classifier",
            description="Text classifier",
            model=ModelRef(name="claude-opus-4-6"),
            system_prompt="Classify the text.",
            tools=[ToolSpec(name="lookup", description="Lookup tool")],
            guardrails=[GuardrailRef(name="pii-filter")],
            output_schema={"type": "object"},
            eval_config=EvalConfig(dimensions=["accuracy"], threshold=0.95),
            cost=CostConfig(max_cost_per_invocation=0.10),
        )
        assert len(spec.tools) == 1
        assert len(spec.guardrails) == 1
        assert spec.eval_config.threshold == 0.95
        assert spec.cost.max_cost_per_invocation == 0.10

    def test_serializable(self) -> None:
        spec = SkillSpec(
            name="s",
            description="d",
            model=ModelRef(name="m"),
            system_prompt="p",
        )
        d = asdict(spec)
        assert d["name"] == "s"
        assert isinstance(d["model"], dict)
        assert isinstance(d["eval_config"], dict)


class TestAgentSpecRAPIDS:
    """Tests for the RAPIDS enrichments on AgentSpec."""

    def test_rapids_defaults(self) -> None:
        spec = AgentSpec(
            name="bot",
            description="d",
            framework="langgraph",
            model=ModelRef(name="m"),
            system_prompt="p",
        )
        assert spec.capabilities == []
        assert spec.decision_loop == {}
        assert spec.state == {}
        assert spec.escalation.target is None
        assert spec.eval_config.threshold == 0.8
        assert spec.cost.max_cost_per_invocation is None
        assert spec.labels == {}

    def test_rapids_full(self) -> None:
        spec = AgentSpec(
            name="support-bot",
            description="Support agent",
            framework="langgraph",
            model=ModelRef(name="claude-opus-4-6"),
            system_prompt="Help users",
            capabilities=["reasoning", "tool-use", "memory"],
            decision_loop={"max_turns": 25, "exit_conditions": ["user_satisfied"]},
            state={"persistence": "redis", "ttl_seconds": 7200},
            escalation=EscalationConfig(target="human", conditions=["low_confidence"]),
            eval_config=EvalConfig(dimensions=["accuracy", "helpfulness"], threshold=0.9),
            cost=CostConfig(max_cost_per_invocation=1.0, daily_budget=500.0),
            labels={"team": "support", "tier": "production"},
        )
        assert "reasoning" in spec.capabilities
        assert spec.decision_loop["max_turns"] == 25
        assert spec.state["persistence"] == "redis"
        assert spec.escalation.target == "human"
        assert spec.eval_config.threshold == 0.9
        assert spec.cost.daily_budget == 500.0
        assert spec.labels["team"] == "support"

    def test_rapids_fields_serializable(self) -> None:
        spec = AgentSpec(
            name="bot",
            description="d",
            framework="f",
            model=ModelRef(name="m"),
            system_prompt="p",
            capabilities=["x"],
            labels={"k": "v"},
        )
        d = asdict(spec)
        assert d["capabilities"] == ["x"]
        assert d["labels"] == {"k": "v"}
        assert isinstance(d["escalation"], dict)
        assert isinstance(d["eval_config"], dict)
        assert isinstance(d["cost"], dict)


class TestNewAgentEventTypes:
    def test_response_event(self) -> None:
        event = AgentEvent(
            type=AgentEventType.RESPONSE,
            data={"result": "answer", "tool": "calc"},
            agent_name="bot",
        )
        assert event.type == AgentEventType.RESPONSE

    def test_escalation_event(self) -> None:
        event = AgentEvent(
            type=AgentEventType.ESCALATION,
            data={"target": "human", "reason": "low confidence"},
        )
        assert event.type == AgentEventType.ESCALATION

    def test_guardrail_trigger_event(self) -> None:
        event = AgentEvent(
            type=AgentEventType.GUARDRAIL_TRIGGER,
            data={"guardrail": "pii-filter", "action": "blocked"},
        )
        assert event.type == AgentEventType.GUARDRAIL_TRIGGER

    def test_cost_checkpoint_event(self) -> None:
        event = AgentEvent(
            type=AgentEventType.COST_CHECKPOINT,
            data={"cost_so_far": 0.42, "budget": 1.0},
        )
        assert event.type == AgentEventType.COST_CHECKPOINT


# ---------------------------------------------------------------------------
# EventInterceptor protocol tests
# ---------------------------------------------------------------------------


class _PassthroughInterceptor:
    """Interceptor that passes events through unchanged."""

    async def intercept(self, event: AgentEvent) -> AgentEvent | None:
        return event


class _HaltingInterceptor:
    """Interceptor that halts the event stream."""

    async def intercept(self, event: AgentEvent) -> AgentEvent | None:
        return None


class _ModifyingInterceptor:
    """Interceptor that modifies event data."""

    async def intercept(self, event: AgentEvent) -> AgentEvent | None:
        event.data["intercepted"] = True
        return event


class TestEventInterceptorProtocol:
    def test_passthrough_satisfies_protocol(self) -> None:
        assert isinstance(_PassthroughInterceptor(), EventInterceptor)

    def test_halting_satisfies_protocol(self) -> None:
        assert isinstance(_HaltingInterceptor(), EventInterceptor)

    def test_non_interceptor_does_not_satisfy(self) -> None:
        class NotAnInterceptor:
            pass

        assert not isinstance(NotAnInterceptor(), EventInterceptor)

    @pytest.mark.asyncio
    async def test_passthrough(self) -> None:
        interceptor = _PassthroughInterceptor()
        event = AgentEvent(type=AgentEventType.TEXT_DELTA, data={"text": "hi"})
        result = await interceptor.intercept(event)
        assert result is event

    @pytest.mark.asyncio
    async def test_halt(self) -> None:
        interceptor = _HaltingInterceptor()
        event = AgentEvent(type=AgentEventType.TEXT_DELTA, data={"text": "hi"})
        result = await interceptor.intercept(event)
        assert result is None

    @pytest.mark.asyncio
    async def test_modify(self) -> None:
        interceptor = _ModifyingInterceptor()
        event = AgentEvent(type=AgentEventType.TEXT_DELTA, data={"text": "hi"})
        result = await interceptor.intercept(event)
        assert result is not None
        assert result.data["intercepted"] is True
