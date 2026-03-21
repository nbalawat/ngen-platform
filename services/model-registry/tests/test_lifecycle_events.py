"""Tests for model registry lifecycle event publishing.

Verifies that CRUD operations publish lifecycle events to the event bus.
Uses InMemoryEventBus — no mocks.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest

from model_registry.app import create_app
from model_registry.repository import ModelRepository
from model_registry.routes import get_repository
from ngen_common.events import InMemoryEventBus, Subjects


@pytest.fixture()
def bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture()
def app(bus):
    test_app = create_app()
    repo = ModelRepository()
    test_app.dependency_overrides[get_repository] = lambda: repo
    # Inject our test bus so we can inspect events
    test_app.state.event_bus = bus
    return test_app


@pytest.fixture()
async def client(app) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture()
def model_payload() -> dict[str, Any]:
    return {
        "name": "test-model",
        "provider": "ANTHROPIC",
        "endpoint": "https://api.anthropic.com/v1/messages",
        "capabilities": ["STREAMING"],
    }


class TestModelRegisteredEvent:
    """Tests for lifecycle.model_registered events."""

    async def test_register_publishes_event(self, client, bus, model_payload):
        resp = await client.post("/api/v1/models", json=model_payload)
        assert resp.status_code == 201

        events = bus.events_for("lifecycle.model_registered")
        assert len(events) == 1
        data = events[0].data
        assert data["name"] == "test-model"
        assert data["provider"] == "ANTHROPIC"
        assert data["is_active"] is True
        assert "model_id" in data

    async def test_register_event_has_correct_subject(self, client, bus, model_payload):
        await client.post("/api/v1/models", json=model_payload)
        events = bus.events_for("lifecycle.model_registered")
        assert events[0].subject == Subjects.LIFECYCLE_MODEL_REGISTERED

    async def test_register_event_source(self, client, bus, model_payload):
        await client.post("/api/v1/models", json=model_payload)
        events = bus.events_for("lifecycle.model_registered")
        assert events[0].source == "model-registry"

    async def test_register_failure_no_event(self, client, bus, model_payload):
        """A failed registration should not publish an event."""
        await client.post("/api/v1/models", json=model_payload)
        # Duplicate should fail
        resp = await client.post("/api/v1/models", json=model_payload)
        assert resp.status_code == 409

        # Only one event from the first successful registration
        events = bus.events_for("lifecycle.model_registered")
        assert len(events) == 1

    async def test_multiple_models_each_publish(self, client, bus):
        for name in ("model-a", "model-b", "model-c"):
            resp = await client.post("/api/v1/models", json={
                "name": name,
                "provider": "ANTHROPIC",
                "endpoint": "https://api.example.com",
            })
            assert resp.status_code == 201

        events = bus.events_for("lifecycle.model_registered")
        assert len(events) == 3
        names = {e.data["name"] for e in events}
        assert names == {"model-a", "model-b", "model-c"}


class TestModelUpdatedEvent:
    """Tests for lifecycle.model_updated events."""

    async def test_update_publishes_event(self, client, bus, model_payload):
        resp = await client.post("/api/v1/models", json=model_payload)
        model_id = resp.json()["id"]

        resp = await client.patch(f"/api/v1/models/{model_id}", json={
            "is_active": False,
        })
        assert resp.status_code == 200

        events = bus.events_for("lifecycle.model_updated")
        assert len(events) == 1
        data = events[0].data
        assert data["model_id"] == model_id
        assert data["is_active"] is False

    async def test_update_nonexistent_no_event(self, client, bus):
        resp = await client.patch(
            "/api/v1/models/00000000-0000-0000-0000-000000000000",
            json={"is_active": False},
        )
        assert resp.status_code == 404
        events = bus.events_for("lifecycle.model_updated")
        assert len(events) == 0


class TestModelDeletedEvent:
    """Tests for lifecycle.model_deleted events."""

    async def test_delete_publishes_event(self, client, bus, model_payload):
        resp = await client.post("/api/v1/models", json=model_payload)
        model_id = resp.json()["id"]

        resp = await client.delete(f"/api/v1/models/{model_id}")
        assert resp.status_code == 204

        events = bus.events_for("lifecycle.model_deleted")
        assert len(events) == 1
        data = events[0].data
        assert data["model_id"] == model_id
        assert data["name"] == "test-model"
        assert data["provider"] == "ANTHROPIC"

    async def test_delete_nonexistent_no_event(self, client, bus):
        resp = await client.delete(
            "/api/v1/models/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404
        events = bus.events_for("lifecycle.model_deleted")
        assert len(events) == 0

    async def test_delete_event_source(self, client, bus, model_payload):
        resp = await client.post("/api/v1/models", json=model_payload)
        model_id = resp.json()["id"]
        await client.delete(f"/api/v1/models/{model_id}")

        events = bus.events_for("lifecycle.model_deleted")
        assert events[0].source == "model-registry"


class TestLifecycleEventFlow:
    """Tests for complete CRUD lifecycle event flow."""

    async def test_full_lifecycle(self, client, bus):
        """Register → Update → Delete should produce 3 distinct events."""
        # Register
        resp = await client.post("/api/v1/models", json={
            "name": "lifecycle-model",
            "provider": "LOCAL",
            "endpoint": "http://localhost:11434",
        })
        assert resp.status_code == 201
        model_id = resp.json()["id"]

        # Update
        resp = await client.patch(f"/api/v1/models/{model_id}", json={
            "name": "lifecycle-model-updated",
        })
        assert resp.status_code == 200

        # Delete
        resp = await client.delete(f"/api/v1/models/{model_id}")
        assert resp.status_code == 204

        # Check all events
        all_lifecycle = bus.events_for("lifecycle.>")
        assert len(all_lifecycle) == 3

        registered = bus.events_for("lifecycle.model_registered")
        updated = bus.events_for("lifecycle.model_updated")
        deleted = bus.events_for("lifecycle.model_deleted")

        assert len(registered) == 1
        assert len(updated) == 1
        assert len(deleted) == 1

        assert registered[0].data["name"] == "lifecycle-model"
        assert updated[0].data["name"] == "lifecycle-model-updated"
        assert deleted[0].data["name"] == "lifecycle-model-updated"
