"""Tests for the adapter plugin registry."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    StateSnapshot,
)
from ngen_framework_core.protocols import ComponentType
from ngen_framework_core.registry import (
    AdapterRegistry,
    ComponentRegistry,
    get_registry,
    reset_registry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockAdapter:
    """Minimal adapter satisfying the FrameworkAdapter protocol."""

    def __init__(self, adapter_name: str = "mock") -> None:
        self._name = adapter_name

    @property
    def name(self) -> str:
        return self._name

    async def create_agent(self, spec: AgentSpec) -> Any:
        return {"name": spec.name}

    async def execute(self, agent: Any, input: AgentInput) -> AsyncIterator[AgentEvent]:
        yield AgentEvent(type=AgentEventType.DONE)

    async def checkpoint(self, agent: Any) -> StateSnapshot:
        return StateSnapshot(agent_name="mock", state={})

    async def restore(self, agent: Any, snapshot: StateSnapshot) -> None:
        pass

    async def teardown(self, agent: Any) -> None:
        pass


class _NotAnAdapter:
    """Does NOT satisfy the FrameworkAdapter protocol."""

    pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    def test_register_and_get(self) -> None:
        registry = AdapterRegistry()
        adapter = _MockAdapter("test-adapter")
        registry.register(adapter)
        assert registry.get("test-adapter") is adapter

    def test_register_rejects_non_adapter(self) -> None:
        registry = AdapterRegistry()
        with pytest.raises(TypeError, match="FrameworkAdapter"):
            registry.register(_NotAnAdapter())  # type: ignore[arg-type]

    def test_register_rejects_duplicate(self) -> None:
        registry = AdapterRegistry()
        registry.register(_MockAdapter("dup"))
        with pytest.raises(ValueError, match="already registered"):
            registry.register(_MockAdapter("dup"))

    def test_get_raises_key_error(self) -> None:
        registry = AdapterRegistry()
        with pytest.raises(KeyError, match="no-such"):
            registry.get("no-such")

    def test_unregister(self) -> None:
        registry = AdapterRegistry()
        registry.register(_MockAdapter("removable"))
        assert "removable" in registry
        registry.unregister("removable")
        assert "removable" not in registry

    def test_unregister_missing_raises(self) -> None:
        registry = AdapterRegistry()
        with pytest.raises(KeyError, match="nope"):
            registry.unregister("nope")

    def test_list_adapters(self) -> None:
        registry = AdapterRegistry()
        registry.register(_MockAdapter("beta"))
        registry.register(_MockAdapter("alpha"))
        assert registry.list_adapters() == ["alpha", "beta"]

    def test_contains(self) -> None:
        registry = AdapterRegistry()
        assert "x" not in registry
        registry.register(_MockAdapter("x"))
        assert "x" in registry

    def test_len(self) -> None:
        registry = AdapterRegistry()
        assert len(registry) == 0
        registry.register(_MockAdapter("a"))
        registry.register(_MockAdapter("b"))
        assert len(registry) == 2

    def test_discover_returns_empty_when_no_entry_points(self) -> None:
        registry = AdapterRegistry()
        # No entry points installed in test env → discover returns empty
        discovered = registry.discover()
        assert isinstance(discovered, list)


class TestDefaultRegistry:
    def setup_method(self) -> None:
        reset_registry()

    def teardown_method(self) -> None:
        reset_registry()

    def test_get_registry_returns_same_instance(self) -> None:
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_reset_clears_registry(self) -> None:
        r1 = get_registry()
        reset_registry()
        r2 = get_registry()
        assert r1 is not r2

    def test_get_adapter_shortcut(self) -> None:
        from ngen_framework_core.registry import get_adapter

        registry = get_registry()
        registry.register(_MockAdapter("shortcut"))
        adapter = get_adapter("shortcut")
        assert adapter.name == "shortcut"


# ---------------------------------------------------------------------------
# ComponentRegistry tests
# ---------------------------------------------------------------------------


class TestComponentRegistry:
    def test_register_and_get(self) -> None:
        registry = ComponentRegistry()
        registry.register("calc", ComponentType.TOOL, {"handler": "calc:run"})
        ct, spec = registry.get("calc")
        assert ct == ComponentType.TOOL
        assert spec["handler"] == "calc:run"

    def test_register_duplicate_raises(self) -> None:
        registry = ComponentRegistry()
        registry.register("calc", ComponentType.TOOL, {})
        with pytest.raises(ValueError, match="already registered"):
            registry.register("calc", ComponentType.TOOL, {})

    def test_get_missing_raises(self) -> None:
        registry = ComponentRegistry()
        with pytest.raises(KeyError, match="not found"):
            registry.get("nope")

    def test_unregister(self) -> None:
        registry = ComponentRegistry()
        registry.register("x", ComponentType.SKILL, {})
        assert "x" in registry
        registry.unregister("x")
        assert "x" not in registry

    def test_unregister_missing_raises(self) -> None:
        registry = ComponentRegistry()
        with pytest.raises(KeyError, match="not found"):
            registry.unregister("nope")

    def test_register_tool_convenience(self) -> None:
        registry = ComponentRegistry()
        registry.register_tool("t1", {"handler": "mod:fn"})
        ct, _ = registry.get("t1")
        assert ct == ComponentType.TOOL

    def test_register_skill_convenience(self) -> None:
        registry = ComponentRegistry()
        registry.register_skill("s1", {"model": "m"})
        ct, _ = registry.get("s1")
        assert ct == ComponentType.SKILL

    def test_register_agent_convenience(self) -> None:
        registry = ComponentRegistry()
        registry.register_agent("a1", {"framework": "langgraph"})
        ct, _ = registry.get("a1")
        assert ct == ComponentType.AGENT

    def test_list_by_type(self) -> None:
        registry = ComponentRegistry()
        registry.register_tool("tool-b", {})
        registry.register_tool("tool-a", {})
        registry.register_skill("skill-x", {})
        registry.register_agent("agent-z", {})

        tools = registry.list_by_type(ComponentType.TOOL)
        assert tools == ["tool-a", "tool-b"]

        skills = registry.list_by_type(ComponentType.SKILL)
        assert skills == ["skill-x"]

        agents = registry.list_by_type(ComponentType.AGENT)
        assert agents == ["agent-z"]

    def test_list_all(self) -> None:
        registry = ComponentRegistry()
        registry.register_tool("b", {})
        registry.register_skill("a", {})
        assert registry.list_all() == ["a", "b"]

    def test_contains_and_len(self) -> None:
        registry = ComponentRegistry()
        assert len(registry) == 0
        assert "x" not in registry
        registry.register_tool("x", {})
        assert len(registry) == 1
        assert "x" in registry
