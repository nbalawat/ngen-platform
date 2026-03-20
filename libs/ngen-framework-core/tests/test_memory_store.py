"""Tests for InMemoryMemoryStore."""

from __future__ import annotations

import time

import pytest

from ngen_framework_core.memory_store import InMemoryMemoryStore
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
        id="",
        memory_type=memory_type,
        scope=scope,
        content=content,
        created_at=kwargs.pop("created_at", time.time()),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Write / Read
# ---------------------------------------------------------------------------


class TestWriteRead:
    @pytest.mark.asyncio
    async def test_write_and_read(self, store, scope_a):
        entry = _entry(scope_a, content="msg1")
        eid = await store.write(entry)
        assert eid
        results = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        assert len(results) == 1
        assert results[0].content == "msg1"

    @pytest.mark.asyncio
    async def test_read_respects_limit(self, store, scope_a):
        for i in range(5):
            await store.write(
                _entry(scope_a, content=f"m{i}", created_at=float(i))
            )
        results = await store.read(scope_a, MemoryType.CONVERSATIONAL, limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_read_returns_newest_first(self, store, scope_a):
        for i in range(3):
            await store.write(
                _entry(scope_a, content=f"m{i}", created_at=float(i + 1))
            )
        results = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        assert results[0].content == "m2"
        assert results[-1].content == "m0"


# ---------------------------------------------------------------------------
# Scope isolation
# ---------------------------------------------------------------------------


class TestScopeIsolation:
    @pytest.mark.asyncio
    async def test_different_scopes_isolated(self, store, scope_a, scope_b):
        await store.write(_entry(scope_a, content="a-msg"))
        await store.write(_entry(scope_b, content="b-msg"))

        results_a = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        results_b = await store.read(scope_b, MemoryType.CONVERSATIONAL)

        assert len(results_a) == 1
        assert results_a[0].content == "a-msg"
        assert len(results_b) == 1
        assert results_b[0].content == "b-msg"


# ---------------------------------------------------------------------------
# Search (cosine similarity)
# ---------------------------------------------------------------------------


class TestSearch:
    @pytest.mark.asyncio
    async def test_cosine_search(self, store, scope_a):
        await store.write(
            _entry(
                scope_a,
                memory_type=MemoryType.KNOWLEDGE_BASE,
                content="dogs",
                embedding=[1.0, 0.0, 0.0],
            )
        )
        await store.write(
            _entry(
                scope_a,
                memory_type=MemoryType.KNOWLEDGE_BASE,
                content="cats",
                embedding=[0.0, 1.0, 0.0],
            )
        )
        results = await store.search(
            scope_a, MemoryType.KNOWLEDGE_BASE, [1.0, 0.0, 0.0], top_k=1
        )
        assert len(results) == 1
        assert results[0].content == "dogs"


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_content(self, store, scope_a):
        eid = await store.write(_entry(scope_a, content="old"))
        ok = await store.update(eid, scope_a, {"content": "new"})
        assert ok
        results = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        assert results[0].content == "new"

    @pytest.mark.asyncio
    async def test_update_summary_id(self, store, scope_a):
        eid = await store.write(_entry(scope_a))
        await store.update(eid, scope_a, {"summary_id": "s1"})
        results = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        assert results[0].summary_id == "s1"

    @pytest.mark.asyncio
    async def test_update_wrong_scope(self, store, scope_a, scope_b):
        eid = await store.write(_entry(scope_a))
        ok = await store.update(eid, scope_b, {"content": "hacked"})
        assert not ok


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete(self, store, scope_a):
        eid = await store.write(_entry(scope_a))
        assert await store.delete(eid, scope_a)
        assert await store.count(scope_a, MemoryType.CONVERSATIONAL) == 0

    @pytest.mark.asyncio
    async def test_delete_wrong_scope(self, store, scope_a, scope_b):
        eid = await store.write(_entry(scope_a))
        assert not await store.delete(eid, scope_b)


# ---------------------------------------------------------------------------
# Delete by scope
# ---------------------------------------------------------------------------


class TestDeleteByScope:
    @pytest.mark.asyncio
    async def test_delete_all(self, store, scope_a):
        await store.write(_entry(scope_a))
        await store.write(
            _entry(scope_a, memory_type=MemoryType.TOOL_LOG, content="log")
        )
        count = await store.delete_by_scope(scope_a)
        assert count == 2
        assert await store.count(scope_a, MemoryType.CONVERSATIONAL) == 0

    @pytest.mark.asyncio
    async def test_delete_specific_type(self, store, scope_a):
        await store.write(_entry(scope_a))
        await store.write(
            _entry(scope_a, memory_type=MemoryType.TOOL_LOG, content="log")
        )
        count = await store.delete_by_scope(scope_a, MemoryType.TOOL_LOG)
        assert count == 1
        assert await store.count(scope_a, MemoryType.CONVERSATIONAL) == 1


# ---------------------------------------------------------------------------
# Expire
# ---------------------------------------------------------------------------


class TestExpire:
    @pytest.mark.asyncio
    async def test_expire_old_entries(self, store, scope_a):
        await store.write(_entry(scope_a, content="old", created_at=100.0))
        await store.write(_entry(scope_a, content="new", created_at=9999999.0))
        count = await store.expire(scope_a, before_timestamp=500.0)
        assert count == 1
        results = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        assert len(results) == 1
        assert results[0].content == "new"


# ---------------------------------------------------------------------------
# TTL expiration on read
# ---------------------------------------------------------------------------


class TestTTLOnRead:
    @pytest.mark.asyncio
    async def test_expired_entries_excluded_on_read(self, store, scope_a):
        await store.write(
            _entry(scope_a, content="expired", created_at=1.0, ttl_seconds=1)
        )
        await store.write(_entry(scope_a, content="active"))
        results = await store.read(scope_a, MemoryType.CONVERSATIONAL)
        assert len(results) == 1
        assert results[0].content == "active"


# ---------------------------------------------------------------------------
# Count
# ---------------------------------------------------------------------------


class TestCount:
    @pytest.mark.asyncio
    async def test_count(self, store, scope_a):
        assert await store.count(scope_a, MemoryType.CONVERSATIONAL) == 0
        await store.write(_entry(scope_a))
        await store.write(_entry(scope_a, content="m2"))
        assert await store.count(scope_a, MemoryType.CONVERSATIONAL) == 2


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


class TestFilters:
    @pytest.mark.asyncio
    async def test_filter_by_role(self, store, scope_a):
        await store.write(_entry(scope_a, content="u", role="user"))
        await store.write(_entry(scope_a, content="a", role="assistant"))
        results = await store.read(
            scope_a, MemoryType.CONVERSATIONAL, filters={"role": "user"}
        )
        assert len(results) == 1
        assert results[0].content == "u"

    @pytest.mark.asyncio
    async def test_filter_unsummarized(self, store, scope_a):
        eid = await store.write(_entry(scope_a, content="summarized"))
        await store.update(eid, scope_a, {"summary_id": "s1"})
        await store.write(_entry(scope_a, content="unsummarized"))
        results = await store.read(
            scope_a,
            MemoryType.CONVERSATIONAL,
            filters={"unsummarized": True},
        )
        assert len(results) == 1
        assert results[0].content == "unsummarized"
