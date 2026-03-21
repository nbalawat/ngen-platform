"""Synchronizes the model gateway router with the model registry service.

The RegistrySync periodically (or on-demand) fetches the list of active
models from the model-registry service and registers them as routes in
the ModelRouter. This allows new models to be added to the registry without
restarting the gateway.

Provider mapping:
    ModelProvider.ANTHROPIC → "anthropic"
    ModelProvider.LOCAL     → "ollama"
    Everything else        → "mock"

Usage:
    sync = RegistrySync(router=model_router, registry_url="http://model-registry:8002")
    await sync.sync()           # one-shot sync
    await sync.start(interval=30)  # background periodic sync
    await sync.stop()
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from model_gateway.router import ModelRouter

logger = logging.getLogger(__name__)

# Map registry provider names to gateway provider names
_PROVIDER_MAP: dict[str, str] = {
    "ANTHROPIC": "anthropic",
    "LOCAL": "ollama",
    "OPENAI": "mock",  # until we have a real OpenAI provider
    "GOOGLE": "mock",
    "AZURE": "mock",
}


@dataclass
class SyncResult:
    """Result of a registry sync operation."""

    models_synced: int = 0
    models_added: int = 0
    models_removed: int = 0
    errors: list[str] = field(default_factory=list)
    success: bool = True


class RegistrySync:
    """Syncs models from the model-registry into the gateway ModelRouter.

    Supports:
    - One-shot sync via sync()
    - Periodic background sync via start()/stop()
    - Tracks which models were synced vs manually registered
    """

    def __init__(
        self,
        router: ModelRouter,
        registry_url: str = "http://localhost:8002",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._router = router
        self._registry_url = registry_url.rstrip("/")
        self._client = http_client
        self._owns_client = http_client is None
        self._synced_models: set[str] = set()  # models added by sync (not manual)
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_result: SyncResult | None = None

    async def sync(self) -> SyncResult:
        """Fetch models from registry and update the router.

        Returns:
            SyncResult with counts and any errors.
        """
        result = SyncResult()
        client = self._client or httpx.AsyncClient(timeout=10.0)

        try:
            resp = await client.get(f"{self._registry_url}/api/v1/models")
            resp.raise_for_status()
            models: list[dict[str, Any]] = resp.json()

            registry_names: set[str] = set()

            for model in models:
                name = model.get("name", "")
                if not name:
                    continue

                # Skip inactive models
                if not model.get("is_active", True):
                    continue

                registry_names.add(name)
                provider_raw = model.get("provider", "LOCAL")
                provider = _PROVIDER_MAP.get(provider_raw, "mock")
                endpoint = model.get("endpoint", "")
                api_key = model.get("metadata", {}).get("api_key", "")

                # Register (or update) in router
                existing = self._router.resolve(name)
                if existing is None:
                    result.models_added += 1
                self._router.register(
                    model_id=name,
                    upstream_url=endpoint,
                    provider=provider,
                    api_key=api_key,
                )
                self._synced_models.add(name)
                result.models_synced += 1

            # Remove models that were previously synced but no longer in registry
            stale = self._synced_models - registry_names
            for name in stale:
                # Only remove if it was added by sync, not manually
                if name in self._synced_models:
                    self._router._routes.pop(name, None)
                    result.models_removed += 1
            self._synced_models -= stale

            result.success = True
            logger.info(
                "Registry sync complete: %d synced, %d added, %d removed",
                result.models_synced, result.models_added, result.models_removed,
            )

        except httpx.HTTPStatusError as e:
            msg = f"Registry returned {e.response.status_code}"
            result.errors.append(msg)
            result.success = False
            logger.warning("Registry sync failed: %s", msg)
        except httpx.ConnectError:
            msg = f"Cannot connect to registry at {self._registry_url}"
            result.errors.append(msg)
            result.success = False
            logger.warning("Registry sync failed: %s", msg)
        except Exception as e:
            msg = f"Unexpected error: {e}"
            result.errors.append(msg)
            result.success = False
            logger.error("Registry sync error: %s", msg, exc_info=True)
        finally:
            if self._owns_client and client is not self._client:
                await client.aclose()

        self._last_result = result
        return result

    async def start(self, interval: float = 30.0) -> None:
        """Start periodic background sync.

        Args:
            interval: Seconds between sync attempts.
        """
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(interval))
        logger.info("Registry sync started (interval=%ss)", interval)

    async def stop(self) -> None:
        """Stop periodic background sync."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Registry sync stopped")

    @property
    def last_result(self) -> SyncResult | None:
        """Get the result of the last sync operation."""
        return self._last_result

    @property
    def synced_models(self) -> set[str]:
        """Get names of models added by sync."""
        return set(self._synced_models)

    async def _loop(self, interval: float) -> None:
        """Background sync loop."""
        while self._running:
            await self.sync()
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
