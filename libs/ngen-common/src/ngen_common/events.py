"""Event bus abstraction for NGEN platform inter-service communication.

Provides a publish/subscribe pattern with two implementations:
1. InMemoryEventBus — for testing and single-process deployments
2. NATSEventBus — for production multi-service deployments

Events are published to named subjects (e.g., "cost.recorded", "audit.policy_evaluated")
and serialized as JSON. Subscribers receive parsed event dicts.

Subjects follow a dot-separated hierarchy:
    cost.recorded
    cost.threshold_exceeded
    audit.policy_evaluated
    audit.workflow_started
    audit.workflow_completed
    lifecycle.agent_created
    lifecycle.agent_deleted

Usage:
    # In-memory (testing)
    bus = InMemoryEventBus()
    await bus.subscribe("cost.*", handler)
    await bus.publish("cost.recorded", {"tenant_id": "acme", "amount": 0.05})

    # NATS (production)
    bus = NATSEventBus(url="nats://localhost:4222")
    await bus.connect()
    await bus.subscribe("cost.>", handler)
    await bus.publish("cost.recorded", {"tenant_id": "acme", "amount": 0.05})
    await bus.disconnect()
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine
from uuid import uuid4

logger = logging.getLogger(__name__)

# Type alias for event handlers
EventHandler = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# Event envelope
# ---------------------------------------------------------------------------


@dataclass
class Event:
    """Standard event envelope for all NGEN events."""

    id: str = field(default_factory=lambda: uuid4().hex)
    subject: str = ""
    source: str = ""  # service that published the event
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps({
            "id": self.id,
            "subject": self.subject,
            "source": self.source,
            "timestamp": self.timestamp,
            "data": self.data,
        }, default=str)

    @classmethod
    def from_json(cls, raw: str | bytes) -> Event:
        """Deserialize from JSON string."""
        d = json.loads(raw)
        return cls(
            id=d.get("id", uuid4().hex),
            subject=d.get("subject", ""),
            source=d.get("source", ""),
            timestamp=d.get("timestamp", time.time()),
            data=d.get("data", {}),
        )


# ---------------------------------------------------------------------------
# EventBus protocol
# ---------------------------------------------------------------------------


class EventBus:
    """Base class for event bus implementations."""

    async def publish(
        self,
        subject: str,
        data: dict[str, Any],
        source: str = "",
    ) -> Event:
        """Publish an event to a subject.

        Args:
            subject: Dot-separated subject (e.g., "cost.recorded").
            data: Event payload.
            source: Source service name.

        Returns:
            The published Event.
        """
        raise NotImplementedError

    async def subscribe(
        self,
        subject: str,
        handler: EventHandler,
    ) -> str:
        """Subscribe to events matching a subject pattern.

        Args:
            subject: Subject pattern. Supports wildcards:
                     "*" matches a single token, ">" matches remaining tokens.
            handler: Async function(subject, data) called for each event.

        Returns:
            Subscription ID for unsubscribe.
        """
        raise NotImplementedError

    async def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscription."""
        raise NotImplementedError

    async def connect(self) -> None:
        """Connect to the event bus (no-op for in-memory)."""
        pass

    async def disconnect(self) -> None:
        """Disconnect from the event bus."""
        pass


# ---------------------------------------------------------------------------
# In-Memory implementation (for testing)
# ---------------------------------------------------------------------------


class InMemoryEventBus(EventBus):
    """In-memory event bus for testing and single-process use.

    Supports wildcard matching:
    - "*" matches exactly one token: "cost.*" matches "cost.recorded"
    - ">" matches one or more tokens: "cost.>" matches "cost.recorded.detail"

    All handlers are called synchronously (in order) during publish().
    Events are stored in a history list for test assertions.
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, tuple[str, EventHandler]] = {}
        self._history: list[Event] = []
        self._connected = True

    async def publish(
        self,
        subject: str,
        data: dict[str, Any],
        source: str = "",
    ) -> Event:
        event = Event(subject=subject, data=data, source=source)
        self._history.append(event)

        # Dispatch to matching subscribers
        for sub_id, (pattern, handler) in list(self._subscriptions.items()):
            if self._matches(pattern, subject):
                try:
                    await handler(subject, data)
                except Exception:
                    logger.exception(
                        "Error in event handler for %s (sub=%s)", subject, sub_id
                    )

        return event

    async def subscribe(
        self,
        subject: str,
        handler: EventHandler,
    ) -> str:
        sub_id = uuid4().hex[:12]
        self._subscriptions[sub_id] = (subject, handler)
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        self._subscriptions.pop(subscription_id, None)

    @property
    def history(self) -> list[Event]:
        """All published events, for test assertions."""
        return list(self._history)

    def events_for(self, subject: str) -> list[Event]:
        """Get events matching a subject pattern."""
        return [e for e in self._history if self._matches(subject, e.subject)]

    def clear(self) -> None:
        """Clear event history."""
        self._history.clear()

    @property
    def subscription_count(self) -> int:
        return len(self._subscriptions)

    @staticmethod
    def _matches(pattern: str, subject: str) -> bool:
        """Match a subject against a NATS-style pattern.

        Rules:
        - "*" matches exactly one dot-separated token
        - ">" matches one or more trailing tokens
        - Literal tokens match exactly
        """
        pattern_parts = pattern.split(".")
        subject_parts = subject.split(".")

        for i, p in enumerate(pattern_parts):
            if p == ">":
                # ">" matches everything remaining
                return i < len(subject_parts)
            if i >= len(subject_parts):
                return False
            if p == "*":
                continue  # matches any single token
            if p != subject_parts[i]:
                return False

        return len(pattern_parts) == len(subject_parts)


# ---------------------------------------------------------------------------
# NATS implementation (production)
# ---------------------------------------------------------------------------


class NATSEventBus(EventBus):
    """NATS-based event bus for production multi-service deployments.

    Requires the `nats-py` package. Falls back gracefully if NATS
    is not reachable (logs warning, events are dropped).
    """

    def __init__(
        self,
        url: str = "nats://localhost:4222",
        source: str = "",
    ) -> None:
        self._url = url
        self._source = source
        self._nc = None  # nats.Client instance
        self._subscriptions: dict[str, Any] = {}

    async def connect(self) -> None:
        """Connect to NATS server."""
        try:
            import nats
            self._nc = await nats.connect(self._url)
            logger.info("Connected to NATS at %s", self._url)
        except ImportError:
            logger.warning("nats-py not installed — NATS event bus unavailable")
            self._nc = None
        except Exception as e:
            logger.warning("Failed to connect to NATS at %s: %s", self._url, e)
            self._nc = None

    async def disconnect(self) -> None:
        """Disconnect from NATS."""
        if self._nc:
            try:
                await self._nc.drain()
            except Exception:
                pass
            self._nc = None

    async def publish(
        self,
        subject: str,
        data: dict[str, Any],
        source: str = "",
    ) -> Event:
        event = Event(
            subject=subject,
            data=data,
            source=source or self._source,
        )

        if self._nc:
            try:
                await self._nc.publish(subject, event.to_json().encode())
            except Exception as e:
                logger.warning("Failed to publish to NATS: %s", e)
        else:
            logger.debug("NATS not connected, event dropped: %s", subject)

        return event

    async def subscribe(
        self,
        subject: str,
        handler: EventHandler,
    ) -> str:
        sub_id = uuid4().hex[:12]

        if self._nc:
            async def _msg_handler(msg):
                try:
                    event = Event.from_json(msg.data)
                    await handler(event.subject, event.data)
                except Exception:
                    logger.exception("Error handling NATS message on %s", subject)

            sub = await self._nc.subscribe(subject, cb=_msg_handler)
            self._subscriptions[sub_id] = sub
        else:
            logger.warning("NATS not connected, subscription to %s not created", subject)

        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        sub = self._subscriptions.pop(subscription_id, None)
        if sub:
            try:
                await sub.unsubscribe()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Standard event subjects
# ---------------------------------------------------------------------------

class Subjects:
    """Standard event subject constants for the NGEN platform."""

    # Cost events
    COST_RECORDED = "cost.recorded"
    COST_THRESHOLD_EXCEEDED = "cost.threshold_exceeded"

    # Audit events
    AUDIT_POLICY_EVALUATED = "audit.policy_evaluated"
    AUDIT_WORKFLOW_STARTED = "audit.workflow_started"
    AUDIT_WORKFLOW_COMPLETED = "audit.workflow_completed"
    AUDIT_WORKFLOW_FAILED = "audit.workflow_failed"
    AUDIT_AUTH_SUCCESS = "audit.auth_success"
    AUDIT_AUTH_FAILURE = "audit.auth_failure"

    # Lifecycle events
    LIFECYCLE_AGENT_CREATED = "lifecycle.agent_created"
    LIFECYCLE_AGENT_DELETED = "lifecycle.agent_deleted"
    LIFECYCLE_SERVER_REGISTERED = "lifecycle.server_registered"
    LIFECYCLE_MODEL_SYNCED = "lifecycle.model_synced"


# ---------------------------------------------------------------------------
# Event publishing helpers
# ---------------------------------------------------------------------------


async def publish_cost_event(
    bus: EventBus,
    tenant_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_cost: float,
    source: str = "model-gateway",
) -> Event:
    """Publish a cost.recorded event."""
    return await bus.publish(
        Subjects.COST_RECORDED,
        {
            "tenant_id": tenant_id,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "total_cost": total_cost,
        },
        source=source,
    )


async def publish_audit_event(
    bus: EventBus,
    subject: str,
    data: dict[str, Any],
    source: str = "",
) -> Event:
    """Publish an audit event."""
    return await bus.publish(subject, data, source=source)
