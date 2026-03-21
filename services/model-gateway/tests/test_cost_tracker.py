"""Tests for the cost tracker."""

from __future__ import annotations

import asyncio

from model_gateway.cost_tracker import CostTracker
from ngen_common.events import InMemoryEventBus, Subjects


class TestCostTracker:
    def test_record_creates_event(self):
        tracker = CostTracker()
        event = tracker.record("t1", "mock-model", 1000, 500)
        assert event.tenant_id == "t1"
        assert event.model == "mock-model"
        assert event.prompt_tokens == 1000
        assert event.completion_tokens == 500
        assert event.total_tokens == 1500

    def test_cost_calculation(self):
        # mock-model: $5/1M input, $25/1M output
        tracker = CostTracker()
        event = tracker.record("t1", "mock-model", 1_000_000, 1_000_000)
        assert event.input_cost == 5.0
        assert event.output_cost == 25.0
        assert event.total_cost == 30.0

    def test_unknown_model_zero_cost(self):
        tracker = CostTracker()
        event = tracker.record("t1", "unknown-model", 1000, 500)
        assert event.total_cost == 0.0

    def test_custom_pricing(self):
        tracker = CostTracker(pricing={"my-model": (10.0, 50.0)})
        event = tracker.record("t1", "my-model", 1_000_000, 1_000_000)
        assert event.input_cost == 10.0
        assert event.output_cost == 50.0

    def test_get_tenant_usage(self):
        tracker = CostTracker()
        tracker.record("t1", "mock-model", 100, 50)
        tracker.record("t1", "mock-model", 200, 100)
        tracker.record("t2", "mock-model", 300, 150)

        usage = tracker.get_tenant_usage("t1")
        assert usage["request_count"] == 2
        assert usage["total_tokens"] == 450

    def test_get_tenant_usage_empty(self):
        tracker = CostTracker()
        usage = tracker.get_tenant_usage("nobody")
        assert usage["request_count"] == 0
        assert usage["total_tokens"] == 0
        assert usage["total_cost"] == 0.0

    def test_clear(self):
        tracker = CostTracker()
        tracker.record("t1", "mock-model", 100, 50)
        assert len(tracker.get_all_events()) == 1
        tracker.clear()
        assert len(tracker.get_all_events()) == 0

    def test_event_has_timestamp(self):
        tracker = CostTracker()
        event = tracker.record("t1", "mock-model", 100, 50)
        assert event.timestamp > 0

    def test_event_has_unique_id(self):
        tracker = CostTracker()
        e1 = tracker.record("t1", "mock-model", 100, 50)
        e2 = tracker.record("t1", "mock-model", 100, 50)
        assert e1.id != e2.id


class TestCostTrackerEventBus:
    """Tests for event bus integration in cost tracker."""

    async def test_publishes_cost_event(self):
        bus = InMemoryEventBus()
        tracker = CostTracker(event_bus=bus)
        tracker.record("acme", "mock-model", 1000, 500)

        # Allow the fire-and-forget task to complete
        await asyncio.sleep(0.05)

        events = bus.events_for("cost.*")
        assert len(events) == 1
        assert events[0].data["tenant_id"] == "acme"
        assert events[0].data["model"] == "mock-model"
        assert events[0].data["total_tokens"] == 1500

    async def test_publishes_multiple_events(self):
        bus = InMemoryEventBus()
        tracker = CostTracker(event_bus=bus)
        tracker.record("acme", "mock-model", 100, 50)
        tracker.record("acme", "mock-model", 200, 100)
        tracker.record("beta", "mock-model-fast", 300, 150)

        await asyncio.sleep(0.05)

        events = bus.events_for("cost.*")
        assert len(events) == 3

    async def test_subscriber_receives_cost_events(self):
        bus = InMemoryEventBus()
        received = []

        async def handler(subject, data):
            received.append(data)

        await bus.subscribe(Subjects.COST_RECORDED, handler)

        tracker = CostTracker(event_bus=bus)
        tracker.record("acme", "mock-model", 1000, 500)

        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0]["tenant_id"] == "acme"
        assert received[0]["total_cost"] > 0

    async def test_no_bus_no_publish(self):
        """Without event bus, record still works normally."""
        tracker = CostTracker()
        event = tracker.record("acme", "mock-model", 1000, 500)
        assert event.total_tokens == 1500
        assert len(tracker.get_all_events()) == 1
