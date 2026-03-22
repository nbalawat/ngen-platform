"""Tests for memory event publishing helpers."""

from __future__ import annotations

import pytest

from ngen_common.events import (
    InMemoryEventBus,
    Subjects,
    publish_memory_event,
)


@pytest.fixture
def bus() -> InMemoryEventBus:
    return InMemoryEventBus()


class TestMemorySubjects:
    def test_memory_subjects_defined(self):
        assert Subjects.MEMORY_WRITTEN == "memory.written"
        assert Subjects.MEMORY_DELETED == "memory.deleted"
        assert Subjects.MEMORY_EXPIRED == "memory.expired"
        assert Subjects.MEMORY_SUMMARIZED == "memory.summarized"


class TestPublishMemoryEvent:
    @pytest.mark.asyncio
    async def test_publish_written_event(self, bus: InMemoryEventBus):
        event = await publish_memory_event(
            bus,
            subject=Subjects.MEMORY_WRITTEN,
            tenant_id="acme",
            agent_name="bot-a",
            memory_type="conversational",
            size_bytes=128,
            token_estimate=32,
            entry_count=1,
        )

        assert event.subject == "memory.written"
        assert event.data["tenant_id"] == "acme"
        assert event.data["agent_name"] == "bot-a"
        assert event.data["memory_type"] == "conversational"
        assert event.data["size_bytes"] == 128
        assert event.data["token_estimate"] == 32
        assert event.data["entry_count"] == 1

    @pytest.mark.asyncio
    async def test_publish_deleted_event(self, bus: InMemoryEventBus):
        await publish_memory_event(
            bus,
            subject=Subjects.MEMORY_DELETED,
            tenant_id="acme",
            agent_name="bot-a",
            memory_type="all",
            entry_count=5,
        )

        events = bus.events_for("memory.deleted")
        assert len(events) == 1
        assert events[0].data["entry_count"] == 5

    @pytest.mark.asyncio
    async def test_wildcard_subscription(self, bus: InMemoryEventBus):
        received: list[dict] = []

        async def handler(subject: str, data: dict):
            received.append({"subject": subject, **data})

        await bus.subscribe("memory.*", handler)

        await publish_memory_event(
            bus,
            subject=Subjects.MEMORY_WRITTEN,
            tenant_id="acme",
            agent_name="bot-a",
            memory_type="conversational",
        )
        await publish_memory_event(
            bus,
            subject=Subjects.MEMORY_DELETED,
            tenant_id="acme",
            agent_name="bot-a",
            memory_type="all",
        )

        assert len(received) == 2
        assert received[0]["subject"] == "memory.written"
        assert received[1]["subject"] == "memory.deleted"

    @pytest.mark.asyncio
    async def test_event_in_bus_history(self, bus: InMemoryEventBus):
        await publish_memory_event(
            bus,
            subject=Subjects.MEMORY_WRITTEN,
            tenant_id="acme",
            agent_name="bot-a",
            memory_type="tool_log",
            size_bytes=256,
            token_estimate=64,
        )

        assert len(bus.history) == 1
        assert bus.history[0].data["memory_type"] == "tool_log"
