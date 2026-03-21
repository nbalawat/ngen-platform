"""Tests for the BudgetTracker — cost event subscriber and daily budget enforcement.

Uses InMemoryEventBus. No mocks.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from unittest.mock import patch

import httpx
import pytest

from governance_service.budget_tracker import BudgetTracker, _today_str
from governance_service.models import PolicyAction, PolicyType, Severity
from governance_service.repository import PolicyRepository
from governance_service.routes import _get_repository
from ngen_common.events import InMemoryEventBus, Subjects


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def repository() -> PolicyRepository:
    return PolicyRepository()


@pytest.fixture()
def bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture()
def tracker(bus: InMemoryEventBus, repository: PolicyRepository) -> BudgetTracker:
    return BudgetTracker(event_bus=bus, repository=repository)


# ---------------------------------------------------------------------------
# Core tracking tests
# ---------------------------------------------------------------------------


class TestCostEventTracking:
    """Tests that cost.recorded events are correctly accumulated."""

    async def test_tracks_single_event(self, bus, tracker):
        await tracker.start()
        await bus.publish("cost.recorded", {
            "tenant_id": "acme",
            "model": "claude-sonnet-4-6",
            "total_cost": 0.05,
            "total_tokens": 1500,
        })

        spend = tracker.get_spend("acme")
        assert spend is not None
        assert spend.total_cost == 0.05
        assert spend.total_tokens == 1500
        assert spend.request_count == 1
        assert spend.date == _today_str()
        await tracker.stop()

    async def test_accumulates_multiple_events(self, bus, tracker):
        await tracker.start()
        await bus.publish("cost.recorded", {
            "tenant_id": "acme",
            "model": "claude-sonnet-4-6",
            "total_cost": 0.03,
            "total_tokens": 1000,
        })
        await bus.publish("cost.recorded", {
            "tenant_id": "acme",
            "model": "claude-haiku-4-5",
            "total_cost": 0.01,
            "total_tokens": 500,
        })

        spend = tracker.get_spend("acme")
        assert spend is not None
        assert spend.total_cost == pytest.approx(0.04)
        assert spend.total_tokens == 1500
        assert spend.request_count == 2
        await tracker.stop()

    async def test_tracks_per_model_spend(self, bus, tracker):
        await tracker.start()
        await bus.publish("cost.recorded", {
            "tenant_id": "acme",
            "model": "claude-sonnet-4-6",
            "total_cost": 0.05,
            "total_tokens": 1000,
        })
        await bus.publish("cost.recorded", {
            "tenant_id": "acme",
            "model": "claude-haiku-4-5",
            "total_cost": 0.01,
            "total_tokens": 500,
        })
        await bus.publish("cost.recorded", {
            "tenant_id": "acme",
            "model": "claude-sonnet-4-6",
            "total_cost": 0.03,
            "total_tokens": 800,
        })

        spend = tracker.get_spend("acme")
        assert spend is not None
        assert spend.models["claude-sonnet-4-6"] == pytest.approx(0.08)
        assert spend.models["claude-haiku-4-5"] == pytest.approx(0.01)
        await tracker.stop()

    async def test_isolates_tenants(self, bus, tracker):
        await tracker.start()
        await bus.publish("cost.recorded", {
            "tenant_id": "acme",
            "model": "test",
            "total_cost": 0.10,
            "total_tokens": 1000,
        })
        await bus.publish("cost.recorded", {
            "tenant_id": "globex",
            "model": "test",
            "total_cost": 0.20,
            "total_tokens": 2000,
        })

        acme = tracker.get_spend("acme")
        globex = tracker.get_spend("globex")
        assert acme is not None
        assert globex is not None
        assert acme.total_cost == pytest.approx(0.10)
        assert globex.total_cost == pytest.approx(0.20)
        await tracker.stop()

    async def test_unknown_tenant_returns_none(self, tracker):
        assert tracker.get_spend("nonexistent") is None

    async def test_get_all_spend(self, bus, tracker):
        await tracker.start()
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 0.05, "total_tokens": 500,
        })
        await bus.publish("cost.recorded", {
            "tenant_id": "globex", "model": "test",
            "total_cost": 0.10, "total_tokens": 1000,
        })

        all_spend = tracker.get_all_spend()
        assert len(all_spend) == 2
        assert "acme" in all_spend
        assert "globex" in all_spend
        await tracker.stop()

    async def test_reset_clears_state(self, bus, tracker):
        await tracker.start()
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 0.05, "total_tokens": 500,
        })
        assert tracker.get_spend("acme") is not None
        tracker.reset()
        assert tracker.get_spend("acme") is None
        await tracker.stop()


# ---------------------------------------------------------------------------
# Threshold enforcement tests
# ---------------------------------------------------------------------------


def _create_budget_policy(
    repo: PolicyRepository,
    namespace: str,
    daily_budget: float,
    alert_threshold: float = 0.8,
) -> None:
    """Helper: create a cost_limit policy with a daily_budget."""
    from governance_service.models import PolicyCreate
    repo.create(PolicyCreate(
        name=f"budget-{namespace}",
        namespace=namespace,
        policy_type=PolicyType.COST_LIMIT,
        action=PolicyAction.WARN,
        severity=Severity.HIGH,
        rules={
            "daily_budget": daily_budget,
            "alert_threshold": alert_threshold,
        },
    ))


class TestThresholdEnforcement:
    """Tests that cost.threshold_exceeded events fire correctly."""

    async def test_threshold_not_fired_below_limit(self, bus, tracker, repository):
        _create_budget_policy(repository, "acme", daily_budget=1.00, alert_threshold=0.8)
        await tracker.start()

        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 0.50, "total_tokens": 1000,
        })

        # No threshold_exceeded events
        exceeded = bus.events_for("cost.threshold_exceeded")
        assert len(exceeded) == 0
        await tracker.stop()

    async def test_threshold_fires_at_80_percent(self, bus, tracker, repository):
        _create_budget_policy(repository, "acme", daily_budget=1.00, alert_threshold=0.8)
        await tracker.start()

        # Push spend to $0.80 (exactly at threshold)
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 0.80, "total_tokens": 5000,
        })

        exceeded = bus.events_for("cost.threshold_exceeded")
        assert len(exceeded) == 1
        data = exceeded[0].data
        assert data["tenant_id"] == "acme"
        assert data["daily_budget"] == 1.00
        assert data["alert_threshold"] == 0.8
        assert data["current_spend"] == 0.80
        assert data["threshold_amount"] == 0.80
        await tracker.stop()

    async def test_threshold_fires_when_crossed_incrementally(self, bus, tracker, repository):
        _create_budget_policy(repository, "acme", daily_budget=1.00, alert_threshold=0.8)
        await tracker.start()

        # First event: $0.50 — below threshold
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 0.50, "total_tokens": 3000,
        })
        assert len(bus.events_for("cost.threshold_exceeded")) == 0

        # Second event: $0.35 — total $0.85, crosses $0.80 threshold
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 0.35, "total_tokens": 2000,
        })
        exceeded = bus.events_for("cost.threshold_exceeded")
        assert len(exceeded) == 1
        assert exceeded[0].data["current_spend"] == pytest.approx(0.85)
        await tracker.stop()

    async def test_threshold_fires_only_once_per_day(self, bus, tracker, repository):
        _create_budget_policy(repository, "acme", daily_budget=1.00, alert_threshold=0.8)
        await tracker.start()

        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 0.85, "total_tokens": 5000,
        })
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 0.50, "total_tokens": 3000,
        })

        # Should only fire once
        exceeded = bus.events_for("cost.threshold_exceeded")
        assert len(exceeded) == 1
        await tracker.stop()

    async def test_custom_alert_threshold(self, bus, tracker, repository):
        _create_budget_policy(repository, "acme", daily_budget=10.00, alert_threshold=0.5)
        await tracker.start()

        # $5.00 is 50% of $10.00 — should trigger at 0.5 threshold
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 5.00, "total_tokens": 10000,
        })

        exceeded = bus.events_for("cost.threshold_exceeded")
        assert len(exceeded) == 1
        assert exceeded[0].data["threshold_amount"] == 5.0
        await tracker.stop()

    async def test_no_policy_no_threshold(self, bus, tracker):
        """Without a cost_limit policy, no thresholds should fire."""
        await tracker.start()
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 999.99, "total_tokens": 1000000,
        })
        exceeded = bus.events_for("cost.threshold_exceeded")
        assert len(exceeded) == 0
        await tracker.stop()

    async def test_disabled_policy_ignored(self, bus, tracker, repository):
        from governance_service.models import PolicyCreate
        policy = repository.create(PolicyCreate(
            name="budget-disabled",
            namespace="acme",
            policy_type=PolicyType.COST_LIMIT,
            action=PolicyAction.WARN,
            rules={"daily_budget": 0.01, "alert_threshold": 0.5},
            enabled=False,
        ))
        await tracker.start()
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 100.0, "total_tokens": 100000,
        })
        exceeded = bus.events_for("cost.threshold_exceeded")
        assert len(exceeded) == 0
        await tracker.stop()

    async def test_different_tenants_independent_thresholds(self, bus, tracker, repository):
        _create_budget_policy(repository, "acme", daily_budget=1.00)
        _create_budget_policy(repository, "globex", daily_budget=2.00)
        await tracker.start()

        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 0.90, "total_tokens": 5000,
        })
        await bus.publish("cost.recorded", {
            "tenant_id": "globex", "model": "test",
            "total_cost": 0.50, "total_tokens": 3000,
        })

        exceeded = bus.events_for("cost.threshold_exceeded")
        # Only acme should trigger (0.90 >= 0.80), globex is below (0.50 < 1.60)
        assert len(exceeded) == 1
        assert exceeded[0].data["tenant_id"] == "acme"
        await tracker.stop()


# ---------------------------------------------------------------------------
# Subscription lifecycle tests
# ---------------------------------------------------------------------------


class TestSubscriptionLifecycle:
    async def test_start_subscribes(self, bus, tracker):
        assert bus.subscription_count == 0
        await tracker.start()
        assert bus.subscription_count == 1
        await tracker.stop()

    async def test_stop_unsubscribes(self, bus, tracker):
        await tracker.start()
        assert bus.subscription_count == 1
        await tracker.stop()
        assert bus.subscription_count == 0

    async def test_events_not_received_after_stop(self, bus, tracker):
        await tracker.start()
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 0.05, "total_tokens": 500,
        })
        assert tracker.get_spend("acme") is not None
        await tracker.stop()

        # Events after stop should not be tracked
        tracker.reset()
        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 0.10, "total_tokens": 1000,
        })
        assert tracker.get_spend("acme") is None

    async def test_double_stop_is_safe(self, bus, tracker):
        await tracker.start()
        await tracker.stop()
        await tracker.stop()  # Should not raise


# ---------------------------------------------------------------------------
# REST endpoint tests
# ---------------------------------------------------------------------------


class TestBudgetEndpoints:
    """Tests for the /api/v1/budgets REST endpoints."""

    @pytest.fixture()
    def governance_app(self, repository):
        """Create app with a known repository for budget testing."""
        import governance_service.routes as routes
        routes._repository = repository
        routes._engine = None
        from governance_service.app import create_app
        return create_app(repository=repository)

    @pytest.fixture()
    async def client(self, governance_app) -> AsyncIterator[httpx.AsyncClient]:
        transport = httpx.ASGITransport(app=governance_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://governance"
        ) as c:
            yield c

    async def test_get_spend_no_data(self, client):
        resp = await client.get("/api/v1/budgets/acme")
        assert resp.status_code == 200
        data = resp.json()
        assert data["namespace"] == "acme"
        assert data["total_cost"] == 0.0
        assert data["request_count"] == 0

    async def test_get_spend_after_event(self, client, governance_app):
        # Publish a cost event through the app's bus
        bus = governance_app.state.event_bus
        tracker = governance_app.state.budget_tracker
        await tracker.start()

        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "claude-sonnet-4-6",
            "total_cost": 0.05, "total_tokens": 1500,
        })

        resp = await client.get("/api/v1/budgets/acme")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == 0.05
        assert data["total_tokens"] == 1500
        assert data["request_count"] == 1
        assert "claude-sonnet-4-6" in data["models"]
        await tracker.stop()

    async def test_list_all_spend(self, client, governance_app):
        bus = governance_app.state.event_bus
        tracker = governance_app.state.budget_tracker
        await tracker.start()

        await bus.publish("cost.recorded", {
            "tenant_id": "acme", "model": "test",
            "total_cost": 0.05, "total_tokens": 500,
        })
        await bus.publish("cost.recorded", {
            "tenant_id": "globex", "model": "test",
            "total_cost": 0.10, "total_tokens": 1000,
        })

        resp = await client.get("/api/v1/budgets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        namespaces = {d["namespace"] for d in data}
        assert "acme" in namespaces
        assert "globex" in namespaces
        await tracker.stop()

    async def test_list_empty(self, client):
        resp = await client.get("/api/v1/budgets")
        assert resp.status_code == 200
        assert resp.json() == []
