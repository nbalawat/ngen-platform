"""Tests for memory protocol types: MemoryType, MemoryScope, MemoryEntry, MemoryPolicy, MemoryStore."""

from __future__ import annotations

import pytest

from ngen_framework_core.protocols import (
    AgentEventType,
    MemoryConfig,
    MemoryEntry,
    MemoryPolicy,
    MemoryScope,
    MemoryStore,
    MemoryType,
)


# ---------------------------------------------------------------------------
# MemoryType enum
# ---------------------------------------------------------------------------


class TestMemoryType:
    def test_all_seven_types(self):
        expected = {
            "conversational",
            "knowledge_base",
            "workflow",
            "toolbox",
            "entity",
            "summary",
            "tool_log",
        }
        assert {mt.value for mt in MemoryType} == expected

    def test_from_value(self):
        assert MemoryType("conversational") is MemoryType.CONVERSATIONAL
        assert MemoryType("tool_log") is MemoryType.TOOL_LOG


# ---------------------------------------------------------------------------
# MemoryScope
# ---------------------------------------------------------------------------


class TestMemoryScope:
    def test_to_prefix_without_thread(self):
        scope = MemoryScope(
            org_id="acme", team_id="eng", project_id="proj1", agent_name="bot"
        )
        assert scope.to_prefix() == "ngen:mem:acme:eng:proj1:bot"

    def test_to_prefix_with_thread(self):
        scope = MemoryScope(
            org_id="acme",
            team_id="eng",
            project_id="proj1",
            agent_name="bot",
            thread_id="t1",
        )
        assert scope.to_prefix() == "ngen:mem:acme:eng:proj1:bot:t1"

    def test_frozen(self):
        scope = MemoryScope(
            org_id="a", team_id="b", project_id="c", agent_name="d"
        )
        with pytest.raises(AttributeError):
            scope.org_id = "x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MemoryEntry
# ---------------------------------------------------------------------------


class TestMemoryEntry:
    def test_defaults(self):
        scope = MemoryScope(
            org_id="a", team_id="b", project_id="c", agent_name="d"
        )
        entry = MemoryEntry(
            id="e1",
            memory_type=MemoryType.CONVERSATIONAL,
            scope=scope,
            content="hello",
        )
        assert entry.metadata == {}
        assert entry.role is None
        assert entry.embedding is None
        assert entry.created_at == 0.0
        assert entry.ttl_seconds is None
        assert entry.summary_id is None

    def test_with_all_fields(self):
        scope = MemoryScope(
            org_id="a", team_id="b", project_id="c", agent_name="d"
        )
        entry = MemoryEntry(
            id="e2",
            memory_type=MemoryType.KNOWLEDGE_BASE,
            scope=scope,
            content="doc content",
            metadata={"source": "wiki"},
            role="user",
            embedding=[0.1, 0.2],
            created_at=1000.0,
            ttl_seconds=3600,
            summary_id="s1",
        )
        assert entry.embedding == [0.1, 0.2]
        assert entry.ttl_seconds == 3600
        assert entry.summary_id == "s1"


# ---------------------------------------------------------------------------
# MemoryPolicy
# ---------------------------------------------------------------------------


class TestMemoryPolicy:
    def test_defaults(self):
        p = MemoryPolicy()
        assert p.max_entries is None
        assert p.ttl_seconds is None
        assert p.summarization_threshold is None
        assert p.retention_days is None

    def test_frozen(self):
        p = MemoryPolicy(max_entries=100)
        with pytest.raises(AttributeError):
            p.max_entries = 200  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MemoryConfig backward compatibility
# ---------------------------------------------------------------------------


class TestMemoryConfig:
    def test_backward_compat_defaults(self):
        cfg = MemoryConfig()
        assert cfg.short_term is True
        assert cfg.long_term is False
        assert cfg.vector_store is None
        assert cfg.ttl_seconds is None

    def test_new_fields(self):
        cfg = MemoryConfig(
            memory_types=[MemoryType.CONVERSATIONAL, MemoryType.ENTITY],
            policy=MemoryPolicy(ttl_seconds=3600),
            embedding_model="all-MiniLM-L6-v2",
            context_budget_tokens=8000,
        )
        assert len(cfg.memory_types) == 2
        assert cfg.policy.ttl_seconds == 3600
        assert cfg.context_budget_tokens == 8000


# ---------------------------------------------------------------------------
# MemoryStore protocol
# ---------------------------------------------------------------------------


class TestMemoryStoreProtocol:
    def test_is_runtime_checkable(self):
        from ngen_framework_core.memory_store import InMemoryMemoryStore

        store = InMemoryMemoryStore()
        assert isinstance(store, MemoryStore)


# ---------------------------------------------------------------------------
# New AgentEventType members
# ---------------------------------------------------------------------------


class TestNewEventTypes:
    def test_memory_write(self):
        assert AgentEventType.MEMORY_WRITE.value == "memory_write"

    def test_memory_expire(self):
        assert AgentEventType.MEMORY_EXPIRE.value == "memory_expire"

    def test_memory_summarize(self):
        assert AgentEventType.MEMORY_SUMMARIZE.value == "memory_summarize"
