"""Tests for the cost tracker."""

from __future__ import annotations

from model_gateway.cost_tracker import CostTracker


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
