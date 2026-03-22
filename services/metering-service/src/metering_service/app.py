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
    # Memory usage tracking
    memory_entries: int = 0
    memory_bytes: int = 0
    memory_tokens: int = 0
    memory_by_agent: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: {"entries": 0, "bytes": 0, "tokens": 0})
    )
    memory_by_type: dict[str, int] = field(default_factory=lambda: defaultdict(int))


class UsageTracker:
    """Tracks usage across all tenants."""

    def __init__(self) -> None:
        self._tenants: dict[str, TenantUsage] = {}
        self._cost_sub_id: str | None = None
        self._memory_sub_id: str | None = None

    async def start(self, bus: EventBus) -> None:
        """Subscribe to cost and memory events."""
        self._cost_sub_id = await bus.subscribe(
            "cost.*", self._handle_cost_event,
        )
        self._memory_sub_id = await bus.subscribe(
            "memory.*", self._handle_memory_event,
        )
        logger.info("UsageTracker subscribed to cost.* and memory.* events")

    async def stop(self, bus: EventBus) -> None:
        """Unsubscribe from events."""
        if self._cost_sub_id:
            await bus.unsubscribe(self._cost_sub_id)
            self._cost_sub_id = None
        if self._memory_sub_id:
            await bus.unsubscribe(self._memory_sub_id)
            self._memory_sub_id = None

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

    async def _handle_memory_event(self, subject: str, data: dict[str, Any]) -> None:
        """Process memory.written / memory.deleted / memory.expired events."""
        tenant_id = data.get("tenant_id", "unknown")
        agent_name = data.get("agent_name", "unknown")
        memory_type = data.get("memory_type", "unknown")
        size_bytes = data.get("size_bytes", 0)
        token_estimate = data.get("token_estimate", 0)
        entry_count = data.get("entry_count", 1)

        usage = self._tenants.get(tenant_id)
        if usage is None:
            usage = TenantUsage(tenant_id=tenant_id)
            self._tenants[tenant_id] = usage

        if subject == "memory.written":
            usage.memory_entries += entry_count
            usage.memory_bytes += size_bytes
            usage.memory_tokens += token_estimate
            agent_stats = usage.memory_by_agent[agent_name]
            agent_stats["entries"] += entry_count
            agent_stats["bytes"] += size_bytes
            agent_stats["tokens"] += token_estimate
            usage.memory_by_type[memory_type] += entry_count
        elif subject in ("memory.deleted", "memory.expired"):
            usage.memory_entries = max(0, usage.memory_entries - entry_count)
            agent_stats = usage.memory_by_agent[agent_name]
            agent_stats["entries"] = max(0, agent_stats["entries"] - entry_count)

    def get_tenant(self, tenant_id: str) -> TenantUsage | None:
        return self._tenants.get(tenant_id)

    def list_tenants(self) -> list[TenantUsage]:
        return list(self._tenants.values())

    def get_summary(self) -> dict:
        """Platform-wide usage summary."""
        total_cost = sum(t.total_cost for t in self._tenants.values())
        total_tokens = sum(t.total_tokens for t in self._tenants.values())
        total_requests = sum(t.total_requests for t in self._tenants.values())
        total_memory_entries = sum(t.memory_entries for t in self._tenants.values())
        total_memory_bytes = sum(t.memory_bytes for t in self._tenants.values())
        total_memory_tokens = sum(t.memory_tokens for t in self._tenants.values())
        return {
            "tenant_count": len(self._tenants),
            "total_cost": round(total_cost, 6),
            "total_tokens": total_tokens,
            "total_requests": total_requests,
            "total_memory_entries": total_memory_entries,
            "total_memory_bytes": total_memory_bytes,
            "total_memory_tokens": total_memory_tokens,
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
            "memory_entries": usage.memory_entries,
            "memory_bytes": usage.memory_bytes,
            "memory_tokens": usage.memory_tokens,
        }

    @application.get("/api/v1/usage/summary")
    async def get_summary() -> dict:
        """Platform-wide usage summary."""
        return tracker.get_summary()

    @application.get("/api/v1/usage/{tenant_id}/memory")
    async def get_tenant_memory_usage(tenant_id: str) -> dict:
        """Get memory usage breakdown for a tenant."""
        usage = tracker.get_tenant(tenant_id)
        if usage is None:
            return {
                "tenant_id": tenant_id,
                "memory_entries": 0,
                "memory_bytes": 0,
                "memory_tokens": 0,
                "by_agent": {},
                "by_type": {},
            }
        return {
            "tenant_id": usage.tenant_id,
            "memory_entries": usage.memory_entries,
            "memory_bytes": usage.memory_bytes,
            "memory_tokens": usage.memory_tokens,
            "by_agent": dict(usage.memory_by_agent),
            "by_type": dict(usage.memory_by_type),
        }

    @application.get("/api/v1/usage/memory/summary")
    async def get_platform_memory_summary() -> dict:
        """Platform-wide memory usage summary."""
        total_entries = sum(t.memory_entries for t in tracker.list_tenants())
        total_bytes = sum(t.memory_bytes for t in tracker.list_tenants())
        total_tokens = sum(t.memory_tokens for t in tracker.list_tenants())
        by_tenant = {
            t.tenant_id: {
                "memory_entries": t.memory_entries,
                "memory_bytes": t.memory_bytes,
                "memory_tokens": t.memory_tokens,
            }
            for t in tracker.list_tenants()
            if t.memory_entries > 0
        }
        return {
            "total_memory_entries": total_entries,
            "total_memory_bytes": total_bytes,
            "total_memory_tokens": total_tokens,
            "tenants_with_memory": len(by_tenant),
            "by_tenant": by_tenant,
        }

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
