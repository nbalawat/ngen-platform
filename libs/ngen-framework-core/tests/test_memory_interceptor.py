"""Tests for MemoryInterceptor."""

from __future__ import annotations

import pytest

from ngen_framework_core.memory_interceptor import MemoryInterceptor
from ngen_framework_core.memory_manager import DefaultMemoryManager
from ngen_framework_core.memory_store import InMemoryMemoryStore
from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    MemoryScope,
    MemoryType,
)


@pytest.fixture
def scope() -> MemoryScope:
    return MemoryScope(
        org_id="acme", team_id="eng", project_id="proj1", agent_name="bot"
    )


@pytest.fixture
def store() -> InMemoryMemoryStore:
    return InMemoryMemoryStore()


@pytest.fixture
def manager(scope, store) -> DefaultMemoryManager:
    return DefaultMemoryManager(scope=scope, store=store)


@pytest.fixture
def interceptor(manager) -> MemoryInterceptor:
    return MemoryInterceptor(manager=manager)


def _event(
    event_type: AgentEventType,
    data: dict | None = None,
    agent_name: str = "bot",
) -> AgentEvent:
    return AgentEvent(
        type=event_type,
        agent_name=agent_name,
        data=data or {},
        timestamp="2026-01-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Event pass-through
# ---------------------------------------------------------------------------


class TestPassThrough:
    @pytest.mark.asyncio
    async def test_always_returns_event(self, interceptor):
        event = _event(AgentEventType.TOOL_CALL_END, {"tool": "search"})
        result = await interceptor.intercept(event)
        assert result is event

    @pytest.mark.asyncio
    async def test_unmapped_event_passes_through(self, interceptor):
        event = _event(AgentEventType.TOOL_CALL_START, {"tool": "search"})
        result = await interceptor.intercept(event)
        assert result is event


# ---------------------------------------------------------------------------
# TOOL_CALL_END → TOOL_LOG
# ---------------------------------------------------------------------------


class TestToolCallEnd:
    @pytest.mark.asyncio
    async def test_writes_to_tool_log(self, interceptor, manager):
        event = _event(
            AgentEventType.TOOL_CALL_END,
            {"tool": "search", "result": "found 5 items"},
        )
        await interceptor.intercept(event)

        entries = await manager.read_memory(MemoryType.TOOL_LOG)
        assert len(entries) == 1
        assert "search" in entries[0].content
        assert entries[0].metadata["event_type"] == "tool_call_end"


# ---------------------------------------------------------------------------
# RESPONSE → CONVERSATIONAL
# ---------------------------------------------------------------------------


class TestResponse:
    @pytest.mark.asyncio
    async def test_writes_to_conversational(self, interceptor, manager):
        event = _event(
            AgentEventType.RESPONSE,
            {"response": "Here is the answer"},
        )
        await interceptor.intercept(event)

        entries = await manager.read_memory(MemoryType.CONVERSATIONAL)
        assert len(entries) == 1
        assert entries[0].role == "assistant"
        assert "answer" in entries[0].content


# ---------------------------------------------------------------------------
# STATE_CHECKPOINT → WORKFLOW
# ---------------------------------------------------------------------------


class TestStateCheckpoint:
    @pytest.mark.asyncio
    async def test_writes_to_workflow(self, interceptor, manager):
        event = _event(
            AgentEventType.STATE_CHECKPOINT,
            {"step": "planning", "progress": 0.5},
        )
        await interceptor.intercept(event)

        entries = await manager.read_memory(MemoryType.WORKFLOW)
        assert len(entries) == 1
        assert "planning" in entries[0].content


# ---------------------------------------------------------------------------
# Unmapped events produce no memory writes
# ---------------------------------------------------------------------------


class TestUnmappedEvents:
    @pytest.mark.asyncio
    async def test_no_writes_for_unmapped(self, interceptor, manager):
        event = _event(AgentEventType.TOOL_CALL_START)
        await interceptor.intercept(event)

        # No memory types should have entries
        for mt in MemoryType:
            entries = await manager.read_memory(mt)
            assert len(entries) == 0


# ---------------------------------------------------------------------------
# Custom event mapping
# ---------------------------------------------------------------------------


class TestCustomMapping:
    @pytest.mark.asyncio
    async def test_custom_mapping(self, manager):
        custom_map = {AgentEventType.TOOL_CALL_START: MemoryType.ENTITY}
        interceptor = MemoryInterceptor(manager=manager, event_mapping=custom_map)

        event = _event(AgentEventType.TOOL_CALL_START, {"tool": "x"})
        await interceptor.intercept(event)

        entities = await manager.read_memory(MemoryType.ENTITY)
        assert len(entities) == 1

        # Default mappings should NOT apply
        tool_logs = await manager.read_memory(MemoryType.TOOL_LOG)
        assert len(tool_logs) == 0


# ---------------------------------------------------------------------------
# Empty event data
# ---------------------------------------------------------------------------


class TestEmptyEventData:
    @pytest.mark.asyncio
    async def test_empty_data_formatted(self, interceptor, manager):
        event = _event(AgentEventType.TOOL_CALL_END, data=None)
        # Replace data with None to test the formatting
        event.data = None
        await interceptor.intercept(event)

        entries = await manager.read_memory(MemoryType.TOOL_LOG)
        assert len(entries) == 1
        assert "[tool_call_end]" in entries[0].content
