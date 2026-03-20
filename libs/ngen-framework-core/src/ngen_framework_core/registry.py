"""Plugin registry for discovering and managing framework adapters and components.

Adapters are discovered via Python entry points (group: ``ngen.adapters``)
and can also be registered programmatically at runtime.

ComponentRegistry manages Tool, Skill, and Agent component specs with
type-based filtering.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Any

from ngen_framework_core.protocols import ComponentType, FrameworkAdapter

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "ngen.adapters"


class AdapterRegistry:
    """Central registry for framework adapters.

    Supports two discovery mechanisms:
    1. **Entry points** — adapters declare themselves via ``pyproject.toml``::

           [project.entry-points."ngen.adapters"]
           langgraph = "langgraph_adapter:LangGraphAdapter"

    2. **Programmatic registration** — ``registry.register(adapter)``
    """

    def __init__(self) -> None:
        self._adapters: dict[str, FrameworkAdapter] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, adapter: FrameworkAdapter) -> None:
        """Register an adapter instance.

        Raises:
            TypeError: If *adapter* does not satisfy the FrameworkAdapter protocol.
            ValueError: If an adapter with the same name is already registered.
        """
        if not isinstance(adapter, FrameworkAdapter):
            raise TypeError(
                f"Expected FrameworkAdapter, got {type(adapter).__name__}. "
                "Adapter must implement the FrameworkAdapter protocol."
            )
        if adapter.name in self._adapters:
            raise ValueError(f"Adapter '{adapter.name}' is already registered")
        self._adapters[adapter.name] = adapter
        logger.info("Registered adapter: %s", adapter.name)

    def unregister(self, name: str) -> None:
        """Remove a previously registered adapter.

        Raises:
            KeyError: If no adapter with *name* is registered.
        """
        if name not in self._adapters:
            raise KeyError(f"No adapter registered with name '{name}'")
        del self._adapters[name]
        logger.info("Unregistered adapter: %s", name)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[str]:
        """Discover adapters from entry points and register them.

        Returns:
            Names of newly discovered adapters.
        """
        discovered: list[str] = []
        eps = entry_points(group=ENTRY_POINT_GROUP)
        for ep in eps:
            if ep.name in self._adapters:
                continue
            try:
                adapter_cls = ep.load()
                adapter = adapter_cls() if isinstance(adapter_cls, type) else adapter_cls
                self.register(adapter)
                discovered.append(ep.name)
            except Exception:
                logger.exception("Failed to load adapter entry point '%s'", ep.name)
        return discovered

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> FrameworkAdapter:
        """Return the adapter registered under *name*.

        Raises:
            KeyError: If no adapter with *name* is found.
        """
        try:
            return self._adapters[name]
        except KeyError:
            available = list(self._adapters.keys())
            raise KeyError(
                f"No adapter registered with name '{name}'. Available: {available}"
            ) from None

    def list_adapters(self) -> list[str]:
        """Return sorted list of registered adapter names."""
        return sorted(self._adapters.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._adapters

    def __len__(self) -> int:
        return len(self._adapters)


# Module-level singleton for convenience
_default_registry: AdapterRegistry | None = None


def get_registry() -> AdapterRegistry:
    """Return the module-level default adapter registry (lazy singleton)."""
    global _default_registry
    if _default_registry is None:
        _default_registry = AdapterRegistry()
    return _default_registry


def reset_registry() -> None:
    """Reset the default registry (primarily for testing)."""
    global _default_registry
    _default_registry = None


def get_adapter(name: str) -> FrameworkAdapter:
    """Shortcut: look up an adapter in the default registry."""
    return get_registry().get(name)


# ---------------------------------------------------------------------------
# Component Registry (RAPIDS — unified Tool/Skill/Agent registry)
# ---------------------------------------------------------------------------


class ComponentRegistry:
    """Registry for platform components (Tools, Skills, Agents).

    Provides type-filtered lookup and convenience methods for each
    component type in the RAPIDS taxonomy.
    """

    def __init__(self) -> None:
        self._components: dict[str, tuple[ComponentType, Any]] = {}

    def register(self, name: str, component_type: ComponentType, spec: Any) -> None:
        """Register a component spec.

        Raises:
            ValueError: If a component with *name* is already registered.
        """
        if name in self._components:
            raise ValueError(f"Component '{name}' is already registered")
        self._components[name] = (component_type, spec)
        logger.info("Registered %s component: %s", component_type.value, name)

    def register_tool(self, name: str, spec: Any) -> None:
        """Convenience: register a Tool component."""
        self.register(name, ComponentType.TOOL, spec)

    def register_skill(self, name: str, spec: Any) -> None:
        """Convenience: register a Skill component."""
        self.register(name, ComponentType.SKILL, spec)

    def register_agent(self, name: str, spec: Any) -> None:
        """Convenience: register an Agent component."""
        self.register(name, ComponentType.AGENT, spec)

    def get(self, name: str) -> tuple[ComponentType, Any]:
        """Return ``(component_type, spec)`` for the given name.

        Raises:
            KeyError: If *name* is not registered.
        """
        try:
            return self._components[name]
        except KeyError:
            raise KeyError(
                f"Component '{name}' not found. Registered: {list(self._components.keys())}"
            ) from None

    def unregister(self, name: str) -> None:
        """Remove a registered component.

        Raises:
            KeyError: If *name* is not registered.
        """
        if name not in self._components:
            raise KeyError(f"Component '{name}' not found")
        del self._components[name]

    def list_by_type(self, component_type: ComponentType) -> list[str]:
        """Return sorted names of components matching the given type."""
        return sorted(
            name for name, (ct, _) in self._components.items() if ct == component_type
        )

    def list_all(self) -> list[str]:
        """Return sorted names of all registered components."""
        return sorted(self._components.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._components

    def __len__(self) -> int:
        return len(self._components)
