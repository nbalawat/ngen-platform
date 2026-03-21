"""Metering Service — aggregates usage data from cost events.

Subscribes to ``cost.recorded`` events via NATS and maintains
per-tenant usage aggregations (daily, hourly). Provides REST
endpoints for querying usage data, billing summaries, and
usage reports.

This is distinct from the governance BudgetTracker — the metering
service focuses on reporting and billing, not enforcement.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from ngen_common.auth import add_auth
from ngen_common.auth_config import make_auth_config
from ngen_common.cors import add_cors
from ngen_common.error_handlers import add_error_handlers
from ngen_common.events import EventBus, InMemoryEventBus, add_event_bus
from ngen_common.observability import add_observability

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Usage tracking data structures
# ---------------------------------------------------------------------------


@dataclass
class TenantUsage:
    """Aggregated usage for a single tenant."""

    tenant_id: str
    total_cost: float = 0.0
    total_tokens: int = 0
    total_requests: int = 0
    models: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    hourly_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    daily_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    last_request_at: float = 0.0


class UsageTracker:
    """Tracks usage across all tenants."""

    def __init__(self) -> None:
        self._tenants: dict[str, TenantUsage] = {}
        self._subscription_id: str | None = None

    async def start(self, bus: EventBus) -> None:
        """Subscribe to cost events."""
        self._subscription_id = await bus.subscribe(
            "cost.*", self._handle_cost_event,
        )
        logger.info("UsageTracker subscribed to cost.* events")

    async def stop(self, bus: EventBus) -> None:
        """Unsubscribe from cost events."""
        if self._subscription_id:
            await bus.unsubscribe(self._subscription_id)
            self._subscription_id = None

    async def _handle_cost_event(self, subject: str, data: dict[str, Any]) -> None:
        """Process a cost.recorded event."""
        tenant_id = data.get("tenant_id", "unknown")
        total_cost = data.get("total_cost", 0.0)
        total_tokens = data.get("total_tokens", 0)
        model = data.get("model", "unknown")

        usage = self._tenants.get(tenant_id)
        if usage is None:
            usage = TenantUsage(tenant_id=tenant_id)
            self._tenants[tenant_id] = usage

        usage.total_cost += total_cost
        usage.total_tokens += total_tokens
        usage.total_requests += 1
        usage.models[model] += total_cost
        usage.last_request_at = time.time()

        # Hourly and daily bucketing
        now = datetime.now(timezone.utc)
        hour_key = now.strftime("%Y-%m-%dT%H:00")
        day_key = now.strftime("%Y-%m-%d")
        usage.hourly_cost[hour_key] += total_cost
        usage.daily_cost[day_key] += total_cost

    def get_tenant(self, tenant_id: str) -> TenantUsage | None:
        return self._tenants.get(tenant_id)

    def list_tenants(self) -> list[TenantUsage]:
        return list(self._tenants.values())

    def get_summary(self) -> dict:
        """Platform-wide usage summary."""
        total_cost = sum(t.total_cost for t in self._tenants.values())
        total_tokens = sum(t.total_tokens for t in self._tenants.values())
        total_requests = sum(t.total_requests for t in self._tenants.values())
        return {
            "tenant_count": len(self._tenants),
            "total_cost": round(total_cost, 6),
            "total_tokens": total_tokens,
            "total_requests": total_requests,
        }


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    usage_tracker: UsageTracker | None = None,
) -> FastAPI:
    application = FastAPI(
        title="NGEN Metering Service",
        version="0.1.0",
        description="Usage aggregation and billing service",
    )

    tracker = usage_tracker or UsageTracker()
    application.state.usage_tracker = tracker

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    # --- Usage endpoints ---

    @application.get("/api/v1/usage")
    async def list_usage() -> list[dict]:
        """List usage for all tenants."""
        return [
            {
                "tenant_id": t.tenant_id,
                "total_cost": round(t.total_cost, 6),
                "total_tokens": t.total_tokens,
                "total_requests": t.total_requests,
                "models": dict(t.models),
            }
            for t in tracker.list_tenants()
        ]

    @application.get("/api/v1/usage/{tenant_id}")
    async def get_usage(tenant_id: str) -> dict:
        """Get detailed usage for a tenant."""
        usage = tracker.get_tenant(tenant_id)
        if usage is None:
            return {
                "tenant_id": tenant_id,
                "total_cost": 0.0,
                "total_tokens": 0,
                "total_requests": 0,
                "models": {},
                "hourly_cost": {},
                "daily_cost": {},
            }
        return {
            "tenant_id": usage.tenant_id,
            "total_cost": round(usage.total_cost, 6),
            "total_tokens": usage.total_tokens,
            "total_requests": usage.total_requests,
            "models": dict(usage.models),
            "hourly_cost": dict(usage.hourly_cost),
            "daily_cost": dict(usage.daily_cost),
            "last_request_at": usage.last_request_at,
        }

    @application.get("/api/v1/usage/summary")
    async def get_summary() -> dict:
        """Platform-wide usage summary."""
        return tracker.get_summary()

    add_error_handlers(application)
    add_cors(application)
    add_observability(application, service_name="metering-service")
    add_auth(application, make_auth_config())
    bus = add_event_bus(application, service_name="metering-service")

    @application.on_event("startup")
    async def _start_tracker() -> None:
        await tracker.start(bus)
        logger.info("UsageTracker started")

    @application.on_event("shutdown")
    async def _stop_tracker() -> None:
        await tracker.stop(bus)

    return application


app = create_app()
