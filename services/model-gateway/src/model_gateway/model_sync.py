"""Model sync subscriber — listens for lifecycle events and updates the router.

Subscribes to ``lifecycle.model_*`` events from the event bus (published by
model-registry) and automatically registers, updates, or removes models
from the gateway's ModelRouter. This enables zero-downtime model
registration — when a model is added to the registry, the gateway
picks it up within seconds without a restart.
"""

from __future__ import annotations

import logging
from typing import Any

from ngen_common.events import EventBus

from model_gateway.router import ModelRouter

logger = logging.getLogger(__name__)

# Map registry provider names to gateway provider names
PROVIDER_MAP: dict[str, str] = {
    "ANTHROPIC": "anthropic",
    "OPENAI": "mock",      # OpenAI-compatible
    "LOCAL": "ollama",
    "GOOGLE": "mock",
    "AZURE": "mock",
}


class ModelSyncSubscriber:
    """Subscribes to model lifecycle events and syncs the ModelRouter.

    Events handled:
    - ``lifecycle.model_registered`` — register new model in router
    - ``lifecycle.model_updated`` — update model route (re-register)
    - ``lifecycle.model_deleted`` — remove model from router
    - ``lifecycle.model_synced`` — bulk sync acknowledgment (logged)
    """

    def __init__(
        self,
        event_bus: EventBus,
        model_router: ModelRouter,
        default_upstream_url: str = "",
    ) -> None:
        self._bus = event_bus
        self._router = model_router
        self._default_upstream_url = default_upstream_url
        self._subscription_id: str | None = None
        self._sync_count: int = 0

    @property
    def sync_count(self) -> int:
        """Number of models synced since start."""
        return self._sync_count

    async def start(self) -> None:
        """Subscribe to lifecycle.* events (filters for model events in handler)."""
        self._subscription_id = await self._bus.subscribe(
            "lifecycle.*",
            self._handle_event,
        )
        logger.info("ModelSyncSubscriber subscribed to lifecycle.* events")

    async def stop(self) -> None:
        """Unsubscribe from lifecycle events."""
        if self._subscription_id:
            await self._bus.unsubscribe(self._subscription_id)
            self._subscription_id = None
            logger.info("ModelSyncSubscriber unsubscribed")

    async def _handle_event(self, subject: str, data: dict[str, Any]) -> None:
        """Dispatch lifecycle events to appropriate handlers."""
        if subject == "lifecycle.model_registered":
            self._on_model_registered(data)
        elif subject == "lifecycle.model_updated":
            self._on_model_updated(data)
        elif subject == "lifecycle.model_deleted":
            self._on_model_deleted(data)
        elif subject == "lifecycle.model_synced":
            logger.info("Model sync event received: %s", data)
        else:
            logger.debug("Ignoring unknown lifecycle event: %s", subject)

    def _on_model_registered(self, data: dict[str, Any]) -> None:
        """Register a new model in the router."""
        name = data.get("name", "")
        provider_raw = data.get("provider", "LOCAL")
        provider = PROVIDER_MAP.get(provider_raw, "mock")
        is_active = data.get("is_active", True)

        if not is_active:
            logger.info("Skipping inactive model: %s", name)
            return

        # Use endpoint from event data or fall back to default
        upstream_url = data.get("endpoint", self._default_upstream_url)

        self._router.register(
            model_id=name,
            upstream_url=upstream_url,
            provider=provider,
        )
        self._sync_count += 1
        logger.info(
            "Model registered via event: %s (provider=%s, upstream=%s)",
            name, provider, upstream_url,
        )

    def _on_model_updated(self, data: dict[str, Any]) -> None:
        """Update model route — re-register or remove if deactivated."""
        name = data.get("name", "")
        is_active = data.get("is_active", True)

        if not is_active:
            self._router.unregister(name)
            self._sync_count += 1
            logger.info("Model deactivated via event: %s", name)
            return

        provider_raw = data.get("provider", "LOCAL")
        provider = PROVIDER_MAP.get(provider_raw, "mock")
        upstream_url = data.get("endpoint", self._default_upstream_url)

        self._router.register(
            model_id=name,
            upstream_url=upstream_url,
            provider=provider,
        )
        self._sync_count += 1
        logger.info("Model updated via event: %s", name)

    def _on_model_deleted(self, data: dict[str, Any]) -> None:
        """Remove model from router."""
        name = data.get("name", "")
        self._router.unregister(name)
        self._sync_count += 1
        logger.info("Model deleted via event: %s", name)
