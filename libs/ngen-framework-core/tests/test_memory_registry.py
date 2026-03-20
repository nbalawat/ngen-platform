"""Tests for MemoryRegistry."""

from __future__ import annotations

import pytest

from ngen_framework_core.memory_manager import DefaultMemoryManager
from ngen_framework_core.memory_registry import MemoryRegistry
from ngen_framework_core.protocols import MemoryConfig, MemoryScope


@pytest.fixture
def scope_a() -> MemoryScope:
    return MemoryScope(
        org_id="acme", team_id="eng", project_id="p1", agent_name="bot-a"
    )


@pytest.fixture
def scope_b() -> MemoryScope:
    return MemoryScope(
        org_id="acme", team_id="eng", project_id="p1", agent_name="bot-b"
    )


@pytest.fixture
def registry() -> MemoryRegistry:
    return MemoryRegistry()


# ---------------------------------------------------------------------------
# Get or create
# ---------------------------------------------------------------------------


class TestGetOrCreate:
    @pytest.mark.asyncio
    async def test_creates_manager(self, registry, scope_a):
        mgr = await registry.get_or_create(scope_a)
        assert isinstance(mgr, DefaultMemoryManager)
        assert mgr.scope == scope_a

    @pytest.mark.asyncio
    async def test_returns_cached_manager(self, registry, scope_a):
        mgr1 = await registry.get_or_create(scope_a)
        mgr2 = await registry.get_or_create(scope_a)
        assert mgr1 is mgr2

    @pytest.mark.asyncio
    async def test_different_scopes_different_managers(
        self, registry, scope_a, scope_b
    ):
        mgr_a = await registry.get_or_create(scope_a)
        mgr_b = await registry.get_or_create(scope_b)
        assert mgr_a is not mgr_b

    @pytest.mark.asyncio
    async def test_with_config(self, registry, scope_a):
        config = MemoryConfig(context_budget_tokens=8000)
        mgr = await registry.get_or_create(scope_a, config=config)
        assert mgr.context_budget_tokens == 8000


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


class TestRemove:
    @pytest.mark.asyncio
    async def test_remove_clears_cache(self, registry, scope_a):
        mgr1 = await registry.get_or_create(scope_a)
        await registry.remove(scope_a)
        mgr2 = await registry.get_or_create(scope_a)
        assert mgr1 is not mgr2

    @pytest.mark.asyncio
    async def test_remove_nonexistent_noop(self, registry, scope_a):
        await registry.remove(scope_a)  # should not raise


# ---------------------------------------------------------------------------
# List scopes
# ---------------------------------------------------------------------------


class TestListScopes:
    @pytest.mark.asyncio
    async def test_list_scopes(self, registry, scope_a, scope_b):
        assert registry.list_scopes() == []
        await registry.get_or_create(scope_a)
        await registry.get_or_create(scope_b)
        scopes = registry.list_scopes()
        assert len(scopes) == 2
        assert scope_a.to_prefix() in scopes
        assert scope_b.to_prefix() in scopes


# ---------------------------------------------------------------------------
# Custom store factory
# ---------------------------------------------------------------------------


class TestCustomFactory:
    @pytest.mark.asyncio
    async def test_custom_factory_called(self, scope_a):
        from ngen_framework_core.memory_store import InMemoryMemoryStore

        custom_store = InMemoryMemoryStore()
        calls = []

        def factory(scope):
            calls.append(scope)
            return custom_store

        registry = MemoryRegistry(default_store_factory=factory)
        mgr = await registry.get_or_create(scope_a)
        assert len(calls) == 1
        assert calls[0] == scope_a
        assert mgr.store is custom_store
