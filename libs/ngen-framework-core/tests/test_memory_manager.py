"""Tests for DefaultMemoryManager."""

from __future__ import annotations

import time

import pytest

from ngen_framework_core.memory_manager import DefaultMemoryManager
from ngen_framework_core.memory_store import InMemoryMemoryStore
from ngen_framework_core.protocols import (
    MemoryPolicy,
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


# ---------------------------------------------------------------------------
# Write + Read
# ---------------------------------------------------------------------------


class TestWriteRead:
    @pytest.mark.asyncio
    async def test_write_and_read(self, manager):
        eid = await manager.write_memory(
            MemoryType.CONVERSATIONAL, "hello", role="user"
        )
        assert eid
        entries = await manager.read_memory(MemoryType.CONVERSATIONAL)
        assert len(entries) == 1
        assert entries[0].content == "hello"
        assert entries[0].role == "user"

    @pytest.mark.asyncio
    async def test_write_multiple_types(self, manager):
        await manager.write_memory(MemoryType.CONVERSATIONAL, "msg")
        await manager.write_memory(MemoryType.TOOL_LOG, "log entry")
        await manager.write_memory(MemoryType.ENTITY, "entity data")

        conv = await manager.read_memory(MemoryType.CONVERSATIONAL)
        logs = await manager.read_memory(MemoryType.TOOL_LOG)
        ents = await manager.read_memory(MemoryType.ENTITY)

        assert len(conv) == 1
        assert len(logs) == 1
        assert len(ents) == 1

    @pytest.mark.asyncio
    async def test_write_with_metadata(self, manager):
        await manager.write_memory(
            MemoryType.WORKFLOW,
            "step1",
            metadata={"step": 1, "status": "done"},
        )
        entries = await manager.read_memory(MemoryType.WORKFLOW)
        assert entries[0].metadata["step"] == 1


# ---------------------------------------------------------------------------
# Context window builder
# ---------------------------------------------------------------------------


class TestBuildContextWindow:
    @pytest.mark.asyncio
    async def test_builds_partitioned_sections(self, manager):
        await manager.write_memory(
            MemoryType.CONVERSATIONAL, "conv msg", role="assistant"
        )
        await manager.write_memory(MemoryType.TOOL_LOG, "tool output")

        ctx = await manager.build_context_window("test query")
        assert "## Conversation Memory" in ctx
        assert "## Tool Log Memory" in ctx
        assert "conv msg" in ctx
        assert "tool output" in ctx

    @pytest.mark.asyncio
    async def test_empty_types_excluded(self, manager):
        await manager.write_memory(MemoryType.CONVERSATIONAL, "msg")
        ctx = await manager.build_context_window("test")
        assert "## Conversation Memory" in ctx
        assert "## Tool Log Memory" not in ctx

    @pytest.mark.asyncio
    async def test_budget_truncation(self, scope, store):
        mgr = DefaultMemoryManager(
            scope=scope, store=store, context_budget_tokens=10
        )
        # Write enough content to exceed a 10-token budget
        await mgr.write_memory(MemoryType.CONVERSATIONAL, "x" * 200)
        ctx = await mgr.build_context_window("test")
        assert "[truncated]" in ctx or len(ctx) < 200

    @pytest.mark.asyncio
    async def test_role_prefix(self, manager):
        await manager.write_memory(
            MemoryType.CONVERSATIONAL, "hello", role="user"
        )
        ctx = await manager.build_context_window("test")
        assert "[user] hello" in ctx


# ---------------------------------------------------------------------------
# Expire old entries
# ---------------------------------------------------------------------------


class TestExpire:
    @pytest.mark.asyncio
    async def test_expire_with_policy(self, scope, store):
        mgr = DefaultMemoryManager(
            scope=scope,
            store=store,
            policy=MemoryPolicy(ttl_seconds=60),
        )
        # Write an old entry
        await mgr.write_memory(MemoryType.CONVERSATIONAL, "old")
        # Manually backdate
        for entry in store._entries.values():
            entry.created_at = time.time() - 120
        # Write a recent entry
        await mgr.write_memory(MemoryType.CONVERSATIONAL, "new")

        deleted = await mgr.expire_old_entries()
        assert deleted == 1
        remaining = await mgr.read_memory(MemoryType.CONVERSATIONAL)
        assert len(remaining) == 1
        assert remaining[0].content == "new"

    @pytest.mark.asyncio
    async def test_expire_no_policy(self, manager):
        await manager.write_memory(MemoryType.CONVERSATIONAL, "msg")
        deleted = await manager.expire_old_entries()
        assert deleted == 0


# ---------------------------------------------------------------------------
# Clip to budget
# ---------------------------------------------------------------------------


class TestClipToBudget:
    @pytest.mark.asyncio
    async def test_clip_removes_oldest(self, manager):
        for i in range(5):
            await manager.write_memory(
                MemoryType.CONVERSATIONAL, f"m{i}"
            )
        deleted = await manager.clip_to_budget(MemoryType.CONVERSATIONAL, 3)
        assert deleted == 2
        remaining = await manager.read_memory(MemoryType.CONVERSATIONAL)
        assert len(remaining) == 3

    @pytest.mark.asyncio
    async def test_clip_under_budget(self, manager):
        await manager.write_memory(MemoryType.CONVERSATIONAL, "m1")
        deleted = await manager.clip_to_budget(MemoryType.CONVERSATIONAL, 10)
        assert deleted == 0


# ---------------------------------------------------------------------------
# Summarize and compact
# ---------------------------------------------------------------------------


class TestSummarizeAndCompact:
    @pytest.mark.asyncio
    async def test_summarize_with_callback(self, store):
        async def mock_summarize(text: str) -> str:
            return f"Summary of {len(text)} chars"

        # Use a scope with thread_id so entries match the scoped read
        thread_scope = MemoryScope(
            org_id="acme",
            team_id="eng",
            project_id="proj1",
            agent_name="bot",
            thread_id="thread-1",
        )
        mgr = DefaultMemoryManager(
            scope=thread_scope, store=store, summarize_fn=mock_summarize
        )
        await mgr.write_memory(
            MemoryType.CONVERSATIONAL, "msg1", role="user"
        )
        await mgr.write_memory(
            MemoryType.CONVERSATIONAL, "msg2", role="assistant"
        )

        summary_id = await mgr.summarize_and_compact("thread-1")
        assert summary_id is not None

        # Summary entry should exist
        summaries = await mgr.read_memory(MemoryType.SUMMARY)
        assert len(summaries) == 1
        assert "Summary of" in summaries[0].content

    @pytest.mark.asyncio
    async def test_summarize_no_callback(self, manager):
        await manager.write_memory(MemoryType.CONVERSATIONAL, "msg")
        result = await manager.summarize_and_compact("thread-1")
        assert result is None


# ---------------------------------------------------------------------------
# Delete by scope
# ---------------------------------------------------------------------------


class TestDeleteByScope:
    @pytest.mark.asyncio
    async def test_delete_all(self, manager):
        await manager.write_memory(MemoryType.CONVERSATIONAL, "m1")
        await manager.write_memory(MemoryType.TOOL_LOG, "log")
        count = await manager.delete_by_scope()
        assert count == 2

    @pytest.mark.asyncio
    async def test_delete_specific_type(self, manager):
        await manager.write_memory(MemoryType.CONVERSATIONAL, "m1")
        await manager.write_memory(MemoryType.TOOL_LOG, "log")
        count = await manager.delete_by_scope(MemoryType.TOOL_LOG)
        assert count == 1
        remaining = await manager.read_memory(MemoryType.CONVERSATIONAL)
        assert len(remaining) == 1


# ---------------------------------------------------------------------------
# Scope isolation between managers
# ---------------------------------------------------------------------------


class TestManagerScopeIsolation:
    @pytest.mark.asyncio
    async def test_two_managers_isolated(self, store):
        scope_a = MemoryScope(
            org_id="a", team_id="t", project_id="p", agent_name="x"
        )
        scope_b = MemoryScope(
            org_id="b", team_id="t", project_id="p", agent_name="x"
        )
        mgr_a = DefaultMemoryManager(scope=scope_a, store=store)
        mgr_b = DefaultMemoryManager(scope=scope_b, store=store)

        await mgr_a.write_memory(MemoryType.CONVERSATIONAL, "from-a")
        await mgr_b.write_memory(MemoryType.CONVERSATIONAL, "from-b")

        entries_a = await mgr_a.read_memory(MemoryType.CONVERSATIONAL)
        entries_b = await mgr_b.read_memory(MemoryType.CONVERSATIONAL)

        assert len(entries_a) == 1
        assert entries_a[0].content == "from-a"
        assert len(entries_b) == 1
        assert entries_b[0].content == "from-b"
