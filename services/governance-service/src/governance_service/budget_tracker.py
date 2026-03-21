"""Budget tracker — consumes cost.recorded events and enforces daily budgets.

Subscribes to ``cost.recorded`` events from the event bus and aggregates
spend per tenant (namespace) per day. When spend crosses the alert_threshold
of a cost_limit policy's daily_budget, a ``cost.threshold_exceeded`` event is
published.

The tracker also exposes helpers for querying current spend, which are
surfaced through REST endpoints.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from ngen_common.events import EventBus, Subjects

from governance_service.repository import PolicyRepository

logger = logging.getLogger(__name__)


@dataclass
class TenantSpend:
    """Daily spend accumulator for a single tenant."""

    date: str  # ISO date string, e.g. "2026-03-21"
    total_cost: float = 0.0
    total_tokens: int = 0
    request_count: int = 0
    models: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    last_updated: float = field(default_factory=time.time)


class BudgetTracker:
    """Tracks daily spend per namespace and enforces budget thresholds.

    Works by subscribing to ``cost.recorded`` events and accumulating
    spend. When a namespace's daily spend crosses the alert_threshold
    fraction of a cost_limit policy's ``daily_budget``, a
    ``cost.threshold_exceeded`` event is published.
    """

    def __init__(
        self,
        event_bus: EventBus,
        repository: PolicyRepository,
    ) -> None:
        self._bus = event_bus
        self._repo = repository
        # {namespace: TenantSpend} — daily accumulator
        self._spend: dict[str, TenantSpend] = {}
        # Track which (namespace, date) thresholds we already fired
        self._threshold_fired: set[tuple[str, str]] = set()
        self._subscription_id: str | None = None

    async def start(self) -> None:
        """Subscribe to cost events."""
        self._subscription_id = await self._bus.subscribe(
            "cost.*", self._handle_cost_event
        )
        logger.info("BudgetTracker subscribed to cost.* events")

    async def stop(self) -> None:
        """Unsubscribe from cost events."""
        if self._subscription_id:
            await self._bus.unsubscribe(self._subscription_id)
            self._subscription_id = None
            logger.info("BudgetTracker unsubscribed from cost events")

    async def _handle_cost_event(self, subject: str, data: dict[str, Any]) -> None:
        """Process a cost.recorded event."""
        tenant_id = data.get("tenant_id", "unknown")
        total_cost = data.get("total_cost", 0.0)
        total_tokens = data.get("total_tokens", 0)
        model = data.get("model", "unknown")

        today = _today_str()

        # Get or create today's accumulator
        spend = self._spend.get(tenant_id)
        if spend is None or spend.date != today:
            # New day — reset
            spend = TenantSpend(date=today)
            self._spend[tenant_id] = spend

        spend.total_cost += total_cost
        spend.total_tokens += total_tokens
        spend.request_count += 1
        spend.models[model] += total_cost
        spend.last_updated = time.time()

        logger.debug(
            "BudgetTracker: tenant=%s daily_cost=%.6f (+%.6f)",
            tenant_id, spend.total_cost, total_cost,
        )

        # Check budget thresholds
        await self._check_thresholds(tenant_id, spend)

    async def _check_thresholds(self, namespace: str, spend: TenantSpend) -> None:
        """Check if any cost_limit policy's daily_budget threshold is breached."""
        policies = self._repo.list(namespace=namespace, policy_type="cost_limit")
        if not policies:
            # Also try "default" namespace for global policies
            policies = self._repo.list(namespace="default", policy_type="cost_limit")

        for policy in policies:
            if not policy.enabled:
                continue
            rules = policy.rules
            daily_budget = rules.get("daily_budget")
            if daily_budget is None or daily_budget <= 0:
                continue

            alert_threshold = rules.get("alert_threshold", 0.8)
            threshold_amount = daily_budget * alert_threshold

            key = (namespace, spend.date)
            if key in self._threshold_fired:
                continue  # Already fired for this tenant+day

            if spend.total_cost >= threshold_amount:
                self._threshold_fired.add(key)
                logger.warning(
                    "Budget threshold exceeded: tenant=%s spend=%.4f threshold=%.4f (%.0f%% of $%.2f)",
                    namespace, spend.total_cost, threshold_amount,
                    alert_threshold * 100, daily_budget,
                )
                await self._bus.publish(
                    Subjects.COST_THRESHOLD_EXCEEDED,
                    {
                        "tenant_id": namespace,
                        "daily_budget": daily_budget,
                        "alert_threshold": alert_threshold,
                        "current_spend": round(spend.total_cost, 6),
                        "threshold_amount": round(threshold_amount, 6),
                        "request_count": spend.request_count,
                        "date": spend.date,
                        "policy_id": policy.id,
                        "policy_name": policy.name,
                    },
                    source="governance-service",
                )

    def get_spend(self, namespace: str) -> TenantSpend | None:
        """Get current daily spend for a namespace.

        Returns None if no spend has been tracked today for this namespace.
        """
        spend = self._spend.get(namespace)
        if spend is None:
            return None
        if spend.date != _today_str():
            return None  # Stale data from a previous day
        return spend

    def get_all_spend(self) -> dict[str, TenantSpend]:
        """Get all tracked spend, filtering stale entries."""
        today = _today_str()
        return {k: v for k, v in self._spend.items() if v.date == today}

    def reset(self) -> None:
        """Clear all tracked spend (for testing)."""
        self._spend.clear()
        self._threshold_fired.clear()


def _today_str() -> str:
    """Return today's date as ISO string in UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
