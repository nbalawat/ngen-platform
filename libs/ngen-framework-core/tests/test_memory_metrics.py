"""Tests for memory metrics (size_bytes, token_estimate) and stats()."""

from __future__ import annotations

import time

import pytest

from ngen_framework_core.memory_manager import DefaultMemoryManager
from ngen_framework_core.memory_store import (
    InMemoryMemoryStore,
    _deserialize_entry,
    _serialize_entry,
)
from ngen_framework_core.protocols import (
    MemoryEntry,
    MemoryScope,
    MemoryType,
)


@pytest.fixture
def store() -> InMemoryMemoryStore:
    return InMemoryMemoryStore()


@pytest.fixture
def scope_a() -> MemoryScope:
    return MemoryScope(
        org_id="acme", team_id="eng", project_id="proj1", agent_name="bot-a"
    )


@pytest.fixture
def scope_b() -> MemoryScope:
    return MemoryScope(
        org_id="other", team_id="ops", project_id="proj2", agent_name="bot-b"
    )


def _entry(
    scope: MemoryScope,
    memory_type: MemoryType = MemoryType.CONVERSATIONAL,
    content: str = "hello",
    **kwargs,
) -> MemoryEntry:
    return MemoryEntry(
        id=kwargs.get("id", ""),
        memory_type=memory_type,
        scope=scope,
        content=content,
        created_at=kwargs.get("created_at", time.time()),
        size_bytes=kwargs.get("size_bytes", len(content.encode("utf-8"))),
        token_estimate=kwargs.get("token_estimate", len(content) // 4),
        ttl_seconds=kwargs.get("ttl_seconds"),
        role=kwargs.get("role"),
    )


# ---------------------------------------------------------------------------
# size_bytes and token_estimate populated on write via manager
# ---------------------------------------------------------------------------


class TestWriteMetrics:
    @pytest.mark.asyncio
    async def test_write_memory_populates_size_fields(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        manager = DefaultMemoryManager(scope=scope_a, store=store)
        content = "Hello, this is a test message with some content."
        entry_id = await manager.write_memory(
            MemoryType.CONVERSATIONAL, content, role="user"
        )

        entries = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.id == entry_id
        assert entry.size_bytes == len(content.encode("utf-8"))
        assert entry.token_estimate == len(content) // 4
        assert entry.size_bytes > 0
        assert entry.token_estimate > 0

    @pytest.mark.asyncio
    async def test_write_memory_unicode_size(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        manager = DefaultMemoryManager(scope=scope_a, store=store)
        content = "Hello \u4e16\u754c"  # "Hello 世界" - multi-byte unicode
        await manager.write_memory(MemoryType.CONVERSATIONAL, content)

        entries = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        entry = entries[0]
        assert entry.size_bytes == len(content.encode("utf-8"))
        # UTF-8 bytes > char count for multi-byte chars
        assert entry.size_bytes > len(content)


# ---------------------------------------------------------------------------
# stats() aggregation
# ---------------------------------------------------------------------------


class TestStats:
    @pytest.mark.asyncio
    async def test_stats_empty_scope(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        result = await store.stats(scope_a)
        assert result == {}

    @pytest.mark.asyncio
    async def test_stats_single_type(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        await store.write(_entry(scope_a, MemoryType.CONVERSATIONAL, "hello"))
        await store.write(_entry(scope_a, MemoryType.CONVERSATIONAL, "world"))

        result = await store.stats(scope_a)
        assert "conversational" in result
        assert result["conversational"]["count"] == 2
        assert result["conversational"]["size_bytes"] == len(b"hello") + len(b"world")
        assert result["conversational"]["token_estimate"] == len("hello") // 4 + len("world") // 4

    @pytest.mark.asyncio
    async def test_stats_multiple_types(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        await store.write(_entry(scope_a, MemoryType.CONVERSATIONAL, "chat msg"))
        await store.write(_entry(scope_a, MemoryType.TOOL_LOG, "tool output here"))
        await store.write(_entry(scope_a, MemoryType.KNOWLEDGE_BASE, "fact"))

        result = await store.stats(scope_a)
        assert len(result) == 3
        assert result["conversational"]["count"] == 1
        assert result["tool_log"]["count"] == 1
        assert result["knowledge_base"]["count"] == 1

    @pytest.mark.asyncio
    async def test_stats_scope_isolation(
        self,
        store: InMemoryMemoryStore,
        scope_a: MemoryScope,
        scope_b: MemoryScope,
    ):
        await store.write(_entry(scope_a, MemoryType.CONVERSATIONAL, "a msg"))
        await store.write(_entry(scope_b, MemoryType.CONVERSATIONAL, "b msg"))

        stats_a = await store.stats(scope_a)
        stats_b = await store.stats(scope_b)

        assert stats_a["conversational"]["count"] == 1
        assert stats_b["conversational"]["count"] == 1

    @pytest.mark.asyncio
    async def test_stats_excludes_expired(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        expired = _entry(
            scope_a,
            MemoryType.CONVERSATIONAL,
            "old",
            created_at=time.time() - 200,
            ttl_seconds=100,
        )
        await store.write(expired)
        await store.write(_entry(scope_a, MemoryType.CONVERSATIONAL, "fresh"))

        result = await store.stats(scope_a)
        assert result["conversational"]["count"] == 1


# ---------------------------------------------------------------------------
# DefaultMemoryManager.get_stats()
# ---------------------------------------------------------------------------


class TestManagerGetStats:
    @pytest.mark.asyncio
    async def test_get_stats_returns_enriched_data(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        manager = DefaultMemoryManager(scope=scope_a, store=store)
        await manager.write_memory(MemoryType.CONVERSATIONAL, "hello world", role="user")
        await manager.write_memory(MemoryType.TOOL_LOG, "tool ran successfully")

        stats = await manager.get_stats()

        assert stats["total_entries"] == 2
        assert stats["total_bytes"] > 0
        assert stats["total_tokens"] > 0
        assert stats["scope"]["agent_name"] == "bot-a"
        assert stats["context_budget_tokens"] == 4000
        assert "conversational" in stats["by_type"]
        assert "tool_log" in stats["by_type"]
        assert stats["policy"]["max_entries"] is None


# ---------------------------------------------------------------------------
# Serialization round-trip preserves new fields
# ---------------------------------------------------------------------------


class TestSerializationRoundTrip:
    def test_size_fields_survive_serialization(self, scope_a: MemoryScope):
        entry = MemoryEntry(
            id="test-1",
            memory_type=MemoryType.CONVERSATIONAL,
            scope=scope_a,
            content="test content",
            size_bytes=42,
            token_estimate=10,
            created_at=time.time(),
        )
        serialized = _serialize_entry(entry)
        restored = _deserialize_entry(serialized)

        assert restored.size_bytes == 42
        assert restored.token_estimate == 10

    def test_missing_size_fields_default_to_zero(self, scope_a: MemoryScope):
        """Backward compat: old entries without size fields get defaults."""
        entry = MemoryEntry(
            id="test-2",
            memory_type=MemoryType.CONVERSATIONAL,
            scope=scope_a,
            content="old entry",
            created_at=time.time(),
        )
        # Simulate old serialization without size fields
        import json

        data = json.loads(_serialize_entry(entry))
        del data["size_bytes"]
        del data["token_estimate"]
        old_json = json.dumps(data)

        restored = _deserialize_entry(old_json)
        assert restored.size_bytes == 0
        assert restored.token_estimate == 0


# ---------------------------------------------------------------------------
# Comprehensive edge case and integration tests
# ---------------------------------------------------------------------------


class TestWriteMetricsEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_content_size_is_zero(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        manager = DefaultMemoryManager(scope=scope_a, store=store)
        await manager.write_memory(MemoryType.CONVERSATIONAL, "")
        entries = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        assert entries[0].size_bytes == 0
        assert entries[0].token_estimate == 0

    @pytest.mark.asyncio
    async def test_large_content_metrics(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        manager = DefaultMemoryManager(scope=scope_a, store=store)
        content = "x" * 10000
        await manager.write_memory(MemoryType.CONVERSATIONAL, content)
        entries = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        assert entries[0].size_bytes == 10000
        assert entries[0].token_estimate == 2500

    @pytest.mark.asyncio
    async def test_emoji_content_size(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        manager = DefaultMemoryManager(scope=scope_a, store=store)
        content = "Hello 🌍🎉"  # emojis are 4 bytes each in UTF-8
        await manager.write_memory(MemoryType.CONVERSATIONAL, content)
        entries = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        assert entries[0].size_bytes == len(content.encode("utf-8"))
        assert entries[0].size_bytes > len(content)

    @pytest.mark.asyncio
    async def test_all_seven_memory_types_populate_metrics(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        manager = DefaultMemoryManager(scope=scope_a, store=store)
        for mt in MemoryType:
            await manager.write_memory(mt, f"content for {mt.value}")

        stats = await manager.get_stats()
        assert stats["total_entries"] == 7
        assert len(stats["by_type"]) == 7
        for mt_value, type_stats in stats["by_type"].items():
            assert type_stats["count"] == 1
            assert type_stats["size_bytes"] > 0


class TestStatsAdvanced:
    @pytest.mark.asyncio
    async def test_stats_size_bytes_accumulate_correctly(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        """Verify exact byte accumulation across multiple entries."""
        contents = ["hello", "world", "testing 123"]
        for c in contents:
            await store.write(_entry(scope_a, MemoryType.CONVERSATIONAL, c))

        result = await store.stats(scope_a)
        expected_bytes = sum(len(c.encode("utf-8")) for c in contents)
        assert result["conversational"]["size_bytes"] == expected_bytes

    @pytest.mark.asyncio
    async def test_stats_with_thread_scoping(
        self, store: InMemoryMemoryStore,
    ):
        """Thread-scoped entries should show up in parent scope stats."""
        parent = MemoryScope(
            org_id="acme", team_id="eng", project_id="proj1", agent_name="bot"
        )
        thread_a = MemoryScope(
            org_id="acme", team_id="eng", project_id="proj1",
            agent_name="bot", thread_id="thread-a"
        )
        thread_b = MemoryScope(
            org_id="acme", team_id="eng", project_id="proj1",
            agent_name="bot", thread_id="thread-b"
        )

        await store.write(_entry(thread_a, content="from thread a"))
        await store.write(_entry(thread_b, content="from thread b"))

        # Parent scope should see both
        parent_stats = await store.stats(parent)
        assert parent_stats["conversational"]["count"] == 2

        # Thread-specific scope should see only its entries
        thread_a_stats = await store.stats(thread_a)
        assert thread_a_stats["conversational"]["count"] == 1

    @pytest.mark.asyncio
    async def test_stats_after_delete(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        """Stats should reflect entries after deletion."""
        e1 = _entry(scope_a, content="entry one")
        e2 = _entry(scope_a, content="entry two")
        await store.write(e1)
        await store.write(e2)

        stats_before = await store.stats(scope_a)
        assert stats_before["conversational"]["count"] == 2

        await store.delete(e1.id, scope_a)

        stats_after = await store.stats(scope_a)
        assert stats_after["conversational"]["count"] == 1

    @pytest.mark.asyncio
    async def test_stats_all_types_simultaneously(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        """Write to all 7 types and verify stats returns all."""
        for mt in MemoryType:
            for i in range(3):
                await store.write(_entry(scope_a, mt, f"{mt.value} entry {i}"))

        result = await store.stats(scope_a)
        assert len(result) == 7
        for mt in MemoryType:
            assert result[mt.value]["count"] == 3


class TestManagerGetStatsAdvanced:
    @pytest.mark.asyncio
    async def test_get_stats_with_custom_policy(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        from ngen_framework_core.protocols import MemoryPolicy
        policy = MemoryPolicy(
            max_entries=100, ttl_seconds=3600,
            summarization_threshold=50, retention_days=30,
        )
        manager = DefaultMemoryManager(
            scope=scope_a, store=store, policy=policy,
            context_budget_tokens=8000,
        )
        await manager.write_memory(MemoryType.CONVERSATIONAL, "test")

        stats = await manager.get_stats()
        assert stats["context_budget_tokens"] == 8000
        assert stats["policy"]["max_entries"] == 100
        assert stats["policy"]["ttl_seconds"] == 3600
        assert stats["policy"]["summarization_threshold"] == 50
        assert stats["policy"]["retention_days"] == 30

    @pytest.mark.asyncio
    async def test_get_stats_empty_manager(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        manager = DefaultMemoryManager(scope=scope_a, store=store)
        stats = await manager.get_stats()
        assert stats["total_entries"] == 0
        assert stats["total_bytes"] == 0
        assert stats["total_tokens"] == 0
        assert stats["by_type"] == {}

    @pytest.mark.asyncio
    async def test_get_stats_scope_metadata(
        self, store: InMemoryMemoryStore
    ):
        scope = MemoryScope(
            org_id="acme-corp", team_id="ml-team",
            project_id="chatbot", agent_name="support-agent",
            thread_id="session-123",
        )
        manager = DefaultMemoryManager(scope=scope, store=store)
        stats = await manager.get_stats()
        assert stats["scope"]["org_id"] == "acme-corp"
        assert stats["scope"]["team_id"] == "ml-team"
        assert stats["scope"]["project_id"] == "chatbot"
        assert stats["scope"]["agent_name"] == "support-agent"
        assert stats["scope"]["thread_id"] == "session-123"


class TestInterceptorEventCallback:
    @pytest.mark.asyncio
    async def test_interceptor_fires_callback_on_write(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        from ngen_framework_core.memory_interceptor import MemoryInterceptor
        from ngen_framework_core.protocols import AgentEvent, AgentEventType

        manager = DefaultMemoryManager(scope=scope_a, store=store)
        callback_calls: list[tuple[str, int, int]] = []

        async def callback(mem_type: str, size_bytes: int, token_estimate: int):
            callback_calls.append((mem_type, size_bytes, token_estimate))

        interceptor = MemoryInterceptor(
            manager=manager, event_callback=callback,
        )

        event = AgentEvent(
            type=AgentEventType.TOOL_CALL_END,
            data={"tool": "search", "result": "found 5 items"},
            agent_name="bot-a",
            timestamp=time.time(),
        )
        result = await interceptor.intercept(event)

        assert result is event  # passthrough
        assert len(callback_calls) == 1
        assert callback_calls[0][0] == "tool_log"
        assert callback_calls[0][1] > 0  # size_bytes
        assert callback_calls[0][2] >= 0  # token_estimate

    @pytest.mark.asyncio
    async def test_interceptor_no_callback_for_unmapped_events(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        from ngen_framework_core.memory_interceptor import MemoryInterceptor
        from ngen_framework_core.protocols import AgentEvent, AgentEventType

        manager = DefaultMemoryManager(scope=scope_a, store=store)
        callback_calls: list = []

        async def callback(mem_type: str, size_bytes: int, token_estimate: int):
            callback_calls.append(mem_type)

        interceptor = MemoryInterceptor(
            manager=manager, event_callback=callback,
        )

        # THINKING is not in the default mapping
        event = AgentEvent(
            type=AgentEventType.THINKING,
            data={"text": "thinking..."},
        )
        await interceptor.intercept(event)
        assert len(callback_calls) == 0

    @pytest.mark.asyncio
    async def test_interceptor_callback_not_required(
        self, store: InMemoryMemoryStore, scope_a: MemoryScope
    ):
        from ngen_framework_core.memory_interceptor import MemoryInterceptor
        from ngen_framework_core.protocols import AgentEvent, AgentEventType

        manager = DefaultMemoryManager(scope=scope_a, store=store)
        # No callback — should work fine
        interceptor = MemoryInterceptor(manager=manager)

        event = AgentEvent(
            type=AgentEventType.RESPONSE,
            data={"text": "hello"},
        )
        result = await interceptor.intercept(event)
        assert result is event

        # Entry was still written
        entries = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        assert len(entries) == 1
