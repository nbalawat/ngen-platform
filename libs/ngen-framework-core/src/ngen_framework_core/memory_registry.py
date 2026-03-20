"""Memory registry for managing per-scope memory manager instances.

The MemoryRegistry maps (namespace, agent) scopes to DefaultMemoryManager
instances with lazy initialization and caching.
"""

from __future__ import annotations

from collections.abc import Callable

from .memory_manager import DefaultMemoryManager
from .memory_store import InMemoryMemoryStore
from .protocols import MemoryConfig, MemoryPolicy, MemoryScope, MemoryStore


class MemoryRegistry:
    """Maps MemoryScope → DefaultMemoryManager with lazy initialization.

    Parameters
    ----------
    default_store_factory:
        Optional factory function that creates a MemoryStore for a given scope.
        If not provided, falls back to InMemoryMemoryStore.
    """

    def __init__(
        self,
        default_store_factory: Callable[[MemoryScope], MemoryStore] | None = None,
    ) -> None:
        self._managers: dict[str, DefaultMemoryManager] = {}
        self._default_store_factory = default_store_factory

    async def get_or_create(
        self,
        scope: MemoryScope,
        config: MemoryConfig | None = None,
    ) -> DefaultMemoryManager:
        """Get or create a memory manager for the given scope.

        First call for a scope creates the manager from the config (or
        defaults). Subsequent calls return the cached instance.
        """
        key = scope.to_prefix()
        if key in self._managers:
            return self._managers[key]

        # Create store via factory or fall back to in-memory
        if self._default_store_factory:
            store = self._default_store_factory(scope)
        else:
            store = InMemoryMemoryStore()

        # Build policy from config
        config = config or MemoryConfig()
        policy = config.policy if config.policy else MemoryPolicy()
        budget = config.context_budget_tokens
        enabled = config.memory_types or None

        manager = DefaultMemoryManager(
            scope=scope,
            store=store,
            policy=policy,
            context_budget_tokens=budget,
            enabled_types=enabled,
        )
        self._managers[key] = manager
        return manager

    async def remove(self, scope: MemoryScope) -> None:
        """Remove a cached manager for the given scope."""
        key = scope.to_prefix()
        self._managers.pop(key, None)

    def list_scopes(self) -> list[str]:
        """List all registered scope prefixes."""
        return list(self._managers.keys())
