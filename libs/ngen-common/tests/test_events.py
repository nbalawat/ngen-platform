"""Tests for the event bus — InMemoryEventBus, Event serialization, subject matching.

Uses real InMemoryEventBus. No mocks.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from ngen_common.events import (
    Event,
    EventBus,
    InMemoryEventBus,
    NATSEventBus,
    Subjects,
    add_event_bus,
    publish_audit_event,
    publish_cost_event,
)


# ---------------------------------------------------------------------------
# Event model tests
# ---------------------------------------------------------------------------


class TestEvent:
    """Tests for the Event data class."""

    def test_default_fields(self):
        e = Event(subject="test.event", data={"key": "value"})
        assert e.subject == "test.event"
        assert e.data == {"key": "value"}
        assert e.id  # non-empty
        assert e.timestamp > 0
        assert e.source == ""

    def test_to_json(self):
        e = Event(subject="cost.recorded", source="gateway", data={"amount": 0.05})
        raw = e.to_json()
        parsed = json.loads(raw)
        assert parsed["subject"] == "cost.recorded"
        assert parsed["source"] == "gateway"
        assert parsed["data"]["amount"] == 0.05
        assert "id" in parsed
        assert "timestamp" in parsed

    def test_from_json(self):
        original = Event(
            id="abc123",
            subject="audit.started",
            source="engine",
            data={"workflow_id": "wf-1"},
        )
        raw = original.to_json()
        restored = Event.from_json(raw)
        assert restored.id == "abc123"
        assert restored.subject == "audit.started"
        assert restored.source == "engine"
        assert restored.data["workflow_id"] == "wf-1"

    def test_roundtrip(self):
        e = Event(subject="test.roundtrip", data={"nested": {"a": 1}})
        restored = Event.from_json(e.to_json())
        assert restored.subject == e.subject
        assert restored.data == e.data
        assert restored.id == e.id

    def test_from_json_bytes(self):
        e = Event(subject="test.bytes", data={"x": 1})
        raw_bytes = e.to_json().encode()
        restored = Event.from_json(raw_bytes)
        assert restored.subject == "test.bytes"


# ---------------------------------------------------------------------------
# Subject matching tests
# ---------------------------------------------------------------------------


class TestSubjectMatching:
    """Tests for NATS-style subject pattern matching."""

    def test_exact_match(self):
        assert InMemoryEventBus._matches("cost.recorded", "cost.recorded") is True

    def test_exact_no_match(self):
        assert InMemoryEventBus._matches("cost.recorded", "cost.deleted") is False

    def test_star_matches_single_token(self):
        assert InMemoryEventBus._matches("cost.*", "cost.recorded") is True
        assert InMemoryEventBus._matches("cost.*", "cost.deleted") is True

    def test_star_does_not_match_multiple_tokens(self):
        assert InMemoryEventBus._matches("cost.*", "cost.recorded.detail") is False

    def test_star_in_middle(self):
        assert InMemoryEventBus._matches("audit.*.completed", "audit.workflow.completed") is True
        assert InMemoryEventBus._matches("audit.*.completed", "audit.policy.completed") is True
        assert InMemoryEventBus._matches("audit.*.completed", "audit.workflow.started") is False

    def test_gt_matches_remaining(self):
        assert InMemoryEventBus._matches("cost.>", "cost.recorded") is True
        assert InMemoryEventBus._matches("cost.>", "cost.recorded.detail") is True
        assert InMemoryEventBus._matches("cost.>", "cost.a.b.c") is True

    def test_gt_requires_at_least_one_token(self):
        assert InMemoryEventBus._matches("cost.>", "cost") is False

    def test_gt_at_top_level(self):
        assert InMemoryEventBus._matches(">", "anything") is True
        assert InMemoryEventBus._matches(">", "a.b.c") is True

    def test_pattern_longer_than_subject(self):
        assert InMemoryEventBus._matches("a.b.c", "a.b") is False

    def test_subject_longer_than_pattern(self):
        assert InMemoryEventBus._matches("a.b", "a.b.c") is False


# ---------------------------------------------------------------------------
# InMemoryEventBus — publish/subscribe tests
# ---------------------------------------------------------------------------


class TestInMemoryEventBus:
    """Tests for the in-memory event bus implementation."""

    async def test_publish_returns_event(self):
        bus = InMemoryEventBus()
        event = await bus.publish("test.event", {"key": "val"})
        assert event.subject == "test.event"
        assert event.data == {"key": "val"}

    async def test_publish_stores_in_history(self):
        bus = InMemoryEventBus()
        await bus.publish("a.b", {"x": 1})
        await bus.publish("c.d", {"y": 2})
        assert len(bus.history) == 2
        assert bus.history[0].subject == "a.b"
        assert bus.history[1].subject == "c.d"

    async def test_subscribe_receives_events(self):
        bus = InMemoryEventBus()
        received = []

        async def handler(subject, data):
            received.append((subject, data))

        await bus.subscribe("test.*", handler)
        await bus.publish("test.event", {"msg": "hello"})

        assert len(received) == 1
        assert received[0] == ("test.event", {"msg": "hello"})

    async def test_subscribe_wildcard(self):
        bus = InMemoryEventBus()
        received = []

        async def handler(subject, data):
            received.append(subject)

        await bus.subscribe("cost.*", handler)
        await bus.publish("cost.recorded", {})
        await bus.publish("cost.deleted", {})
        await bus.publish("audit.started", {})  # should NOT match

        assert received == ["cost.recorded", "cost.deleted"]

    async def test_subscribe_gt_wildcard(self):
        bus = InMemoryEventBus()
        received = []

        async def handler(subject, data):
            received.append(subject)

        await bus.subscribe("audit.>", handler)
        await bus.publish("audit.started", {})
        await bus.publish("audit.workflow.completed", {})
        await bus.publish("cost.recorded", {})  # should NOT match

        assert received == ["audit.started", "audit.workflow.completed"]

    async def test_multiple_subscribers(self):
        bus = InMemoryEventBus()
        received_a = []
        received_b = []

        async def handler_a(subject, data):
            received_a.append(subject)

        async def handler_b(subject, data):
            received_b.append(subject)

        await bus.subscribe("cost.*", handler_a)
        await bus.subscribe("cost.recorded", handler_b)
        await bus.publish("cost.recorded", {})

        assert len(received_a) == 1
        assert len(received_b) == 1

    async def test_unsubscribe(self):
        bus = InMemoryEventBus()
        received = []

        async def handler(subject, data):
            received.append(subject)

        sub_id = await bus.subscribe("test.*", handler)
        await bus.publish("test.a", {})
        assert len(received) == 1

        await bus.unsubscribe(sub_id)
        await bus.publish("test.b", {})
        assert len(received) == 1  # no new events

    async def test_subscription_count(self):
        bus = InMemoryEventBus()

        async def handler(s, d):
            pass

        id1 = await bus.subscribe("a.*", handler)
        id2 = await bus.subscribe("b.*", handler)
        assert bus.subscription_count == 2

        await bus.unsubscribe(id1)
        assert bus.subscription_count == 1

    async def test_events_for_filter(self):
        bus = InMemoryEventBus()
        await bus.publish("cost.recorded", {"amount": 0.01})
        await bus.publish("audit.started", {"wf": "1"})
        await bus.publish("cost.recorded", {"amount": 0.02})

        cost_events = bus.events_for("cost.*")
        assert len(cost_events) == 2
        assert all(e.subject == "cost.recorded" for e in cost_events)

    async def test_clear_history(self):
        bus = InMemoryEventBus()
        await bus.publish("test.a", {})
        await bus.publish("test.b", {})
        bus.clear()
        assert len(bus.history) == 0

    async def test_handler_error_does_not_break_bus(self):
        bus = InMemoryEventBus()
        received = []

        async def bad_handler(subject, data):
            raise RuntimeError("handler crash")

        async def good_handler(subject, data):
            received.append(subject)

        await bus.subscribe("test.*", bad_handler)
        await bus.subscribe("test.*", good_handler)

        # Should not raise — bad handler error is logged, good handler still runs
        await bus.publish("test.event", {})
        assert len(received) == 1

    async def test_publish_with_source(self):
        bus = InMemoryEventBus()
        event = await bus.publish("test.event", {}, source="my-service")
        assert event.source == "my-service"


# ---------------------------------------------------------------------------
# Publishing helper tests
# ---------------------------------------------------------------------------


class TestPublishHelpers:
    """Tests for convenience publish functions."""

    async def test_publish_cost_event(self):
        bus = InMemoryEventBus()
        event = await publish_cost_event(
            bus,
            tenant_id="acme",
            model="claude-sonnet-4-6",
            prompt_tokens=1000,
            completion_tokens=500,
            total_cost=0.0105,
            source="model-gateway",
        )
        assert event.subject == Subjects.COST_RECORDED
        assert event.data["tenant_id"] == "acme"
        assert event.data["model"] == "claude-sonnet-4-6"
        assert event.data["total_tokens"] == 1500
        assert event.data["total_cost"] == 0.0105
        assert event.source == "model-gateway"

    async def test_publish_audit_event(self):
        bus = InMemoryEventBus()
        event = await publish_audit_event(
            bus,
            subject=Subjects.AUDIT_WORKFLOW_STARTED,
            data={"workflow_id": "wf-123", "namespace": "prod"},
            source="workflow-engine",
        )
        assert event.subject == Subjects.AUDIT_WORKFLOW_STARTED
        assert event.data["workflow_id"] == "wf-123"

    async def test_cost_event_received_by_subscriber(self):
        bus = InMemoryEventBus()
        received = []

        async def handler(subject, data):
            received.append(data)

        await bus.subscribe("cost.*", handler)
        await publish_cost_event(
            bus, tenant_id="acme", model="test",
            prompt_tokens=100, completion_tokens=50, total_cost=0.001,
        )

        assert len(received) == 1
        assert received[0]["tenant_id"] == "acme"


# ---------------------------------------------------------------------------
# Subjects constants tests
# ---------------------------------------------------------------------------


class TestSubjects:
    """Tests that standard subject constants are defined."""

    def test_cost_subjects(self):
        assert Subjects.COST_RECORDED == "cost.recorded"
        assert Subjects.COST_THRESHOLD_EXCEEDED == "cost.threshold_exceeded"

    def test_audit_subjects(self):
        assert Subjects.AUDIT_WORKFLOW_STARTED == "audit.workflow_started"
        assert Subjects.AUDIT_WORKFLOW_COMPLETED == "audit.workflow_completed"
        assert Subjects.AUDIT_POLICY_EVALUATED == "audit.policy_evaluated"

    def test_lifecycle_subjects(self):
        assert Subjects.LIFECYCLE_AGENT_CREATED == "lifecycle.agent_created"
        assert Subjects.LIFECYCLE_SERVER_REGISTERED == "lifecycle.server_registered"


# ---------------------------------------------------------------------------
# NATSEventBus (graceful degradation without real NATS)
# ---------------------------------------------------------------------------


class TestNATSEventBusGraceful:
    """Tests that NATSEventBus handles missing NATS gracefully."""

    async def test_publish_without_connection(self):
        """Publishing without a connection should not raise."""
        bus = NATSEventBus(url="nats://localhost:4222")
        # Don't call connect — _nc is None
        event = await bus.publish("test.event", {"x": 1})
        assert event.subject == "test.event"

    async def test_subscribe_without_connection(self):
        """Subscribing without a connection should not raise."""
        bus = NATSEventBus(url="nats://localhost:4222")

        async def handler(s, d):
            pass

        sub_id = await bus.subscribe("test.*", handler)
        assert sub_id  # returns an ID even without connection

    async def test_disconnect_without_connection(self):
        """Disconnecting without connection should not raise."""
        bus = NATSEventBus(url="nats://localhost:4222")
        await bus.disconnect()  # no-op, no error

    async def test_connect_unreachable_server(self):
        """Connecting to unreachable server should not raise."""
        bus = NATSEventBus(
            url="nats://127.0.0.1:19999",
            connect_timeout=1.0,
            max_reconnect_attempts=0,
        )
        await bus.connect()  # should log warning, not raise
        assert bus._nc is None


# ---------------------------------------------------------------------------
# add_event_bus helper tests
# ---------------------------------------------------------------------------


class TestAddEventBus:
    """Tests for the add_event_bus FastAPI integration helper."""

    def test_creates_inmemory_bus_when_no_nats_url(self):
        """Without NATS_URL, should create InMemoryEventBus."""
        import os
        from fastapi import FastAPI

        os.environ.pop("NATS_URL", None)
        app = FastAPI()
        bus = add_event_bus(app, service_name="test-service")
        assert isinstance(bus, InMemoryEventBus)
        assert app.state.event_bus is bus

    def test_creates_nats_bus_when_url_provided(self):
        """With explicit nats_url, should create NATSEventBus."""
        from fastapi import FastAPI

        app = FastAPI()
        bus = add_event_bus(
            app, service_name="test-service",
            nats_url="nats://localhost:14222",  # intentionally unused port
        )
        assert isinstance(bus, NATSEventBus)
        assert app.state.event_bus is bus

    def test_creates_nats_bus_from_env(self):
        """Should read NATS_URL from environment."""
        import os
        from fastapi import FastAPI

        os.environ["NATS_URL"] = "nats://env-host:4222"
        try:
            app = FastAPI()
            bus = add_event_bus(app, service_name="test-service")
            assert isinstance(bus, NATSEventBus)
            assert bus._url == "nats://env-host:4222"
        finally:
            os.environ.pop("NATS_URL", None)

    def test_bus_stored_on_app_state(self):
        """Event bus should be accessible via app.state.event_bus."""
        import os
        from fastapi import FastAPI

        os.environ.pop("NATS_URL", None)
        app = FastAPI()
        bus = add_event_bus(app, service_name="test-service")
        assert hasattr(app.state, "event_bus")
        assert app.state.event_bus is bus
