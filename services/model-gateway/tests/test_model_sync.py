"""Tests for ModelSyncSubscriber — event-driven model routing updates.

Uses InMemoryEventBus and real ModelRouter. No mocks.
"""

from __future__ import annotations

import pytest

from model_gateway.model_sync import ModelSyncSubscriber, PROVIDER_MAP
from model_gateway.router import ModelRouter
from ngen_common.events import InMemoryEventBus


@pytest.fixture()
def bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture()
def router() -> ModelRouter:
    return ModelRouter()


@pytest.fixture()
def subscriber(bus, router) -> ModelSyncSubscriber:
    return ModelSyncSubscriber(
        event_bus=bus,
        model_router=router,
        default_upstream_url="http://default:8000",
    )


# ---------------------------------------------------------------------------
# Registration events
# ---------------------------------------------------------------------------


class TestModelRegistered:
    async def test_registers_model_in_router(self, bus, router, subscriber):
        await subscriber.start()
        await bus.publish("lifecycle.model_registered", {
            "model_id": "abc-123",
            "name": "test-model",
            "provider": "ANTHROPIC",
            "is_active": True,
        })

        route = router.resolve("test-model")
        assert route is not None
        assert route.provider == "anthropic"
        assert route.upstream_url == "http://default:8000"
        await subscriber.stop()

    async def test_registers_with_endpoint(self, bus, router, subscriber):
        await subscriber.start()
        await bus.publish("lifecycle.model_registered", {
            "name": "custom-model",
            "provider": "LOCAL",
            "is_active": True,
            "endpoint": "http://ollama:11434",
        })

        route = router.resolve("custom-model")
        assert route is not None
        assert route.upstream_url == "http://ollama:11434"
        assert route.provider == "ollama"
        await subscriber.stop()

    async def test_skips_inactive_model(self, bus, router, subscriber):
        await subscriber.start()
        await bus.publish("lifecycle.model_registered", {
            "name": "disabled-model",
            "provider": "ANTHROPIC",
            "is_active": False,
        })

        assert router.resolve("disabled-model") is None
        await subscriber.stop()

    async def test_increments_sync_count(self, bus, router, subscriber):
        await subscriber.start()
        assert subscriber.sync_count == 0

        await bus.publish("lifecycle.model_registered", {
            "name": "m1", "provider": "LOCAL", "is_active": True,
        })
        assert subscriber.sync_count == 1

        await bus.publish("lifecycle.model_registered", {
            "name": "m2", "provider": "LOCAL", "is_active": True,
        })
        assert subscriber.sync_count == 2
        await subscriber.stop()

    async def test_all_provider_mappings(self, bus, router, subscriber):
        await subscriber.start()
        for registry_provider, gateway_provider in PROVIDER_MAP.items():
            name = f"model-{registry_provider.lower()}"
            await bus.publish("lifecycle.model_registered", {
                "name": name,
                "provider": registry_provider,
                "is_active": True,
            })
            route = router.resolve(name)
            assert route is not None
            assert route.provider == gateway_provider, (
                f"Expected {gateway_provider} for {registry_provider}, "
                f"got {route.provider}"
            )
        await subscriber.stop()


# ---------------------------------------------------------------------------
# Update events
# ---------------------------------------------------------------------------


class TestModelUpdated:
    async def test_updates_existing_model(self, bus, router, subscriber):
        router.register("existing", "http://old:8000", provider="mock")
        await subscriber.start()

        await bus.publish("lifecycle.model_updated", {
            "name": "existing",
            "provider": "ANTHROPIC",
            "is_active": True,
            "endpoint": "http://new:8000",
        })

        route = router.resolve("existing")
        assert route is not None
        assert route.upstream_url == "http://new:8000"
        assert route.provider == "anthropic"
        await subscriber.stop()

    async def test_deactivation_removes_model(self, bus, router, subscriber):
        router.register("to-deactivate", "http://x:8000", provider="mock")
        await subscriber.start()

        await bus.publish("lifecycle.model_updated", {
            "name": "to-deactivate",
            "provider": "ANTHROPIC",
            "is_active": False,
        })

        assert router.resolve("to-deactivate") is None
        await subscriber.stop()

    async def test_reactivation_registers_model(self, bus, router, subscriber):
        await subscriber.start()
        # First deactivate
        await bus.publish("lifecycle.model_updated", {
            "name": "toggle", "provider": "LOCAL", "is_active": False,
        })
        assert router.resolve("toggle") is None

        # Then reactivate
        await bus.publish("lifecycle.model_updated", {
            "name": "toggle", "provider": "LOCAL", "is_active": True,
            "endpoint": "http://reactivated:8000",
        })
        route = router.resolve("toggle")
        assert route is not None
        assert route.upstream_url == "http://reactivated:8000"
        await subscriber.stop()


# ---------------------------------------------------------------------------
# Delete events
# ---------------------------------------------------------------------------


class TestModelDeleted:
    async def test_removes_model_from_router(self, bus, router, subscriber):
        router.register("to-delete", "http://x:8000", provider="mock")
        assert router.resolve("to-delete") is not None

        await subscriber.start()
        await bus.publish("lifecycle.model_deleted", {
            "model_id": "abc-123",
            "name": "to-delete",
            "provider": "LOCAL",
        })

        assert router.resolve("to-delete") is None
        await subscriber.stop()

    async def test_delete_nonexistent_is_safe(self, bus, router, subscriber):
        await subscriber.start()
        # Should not raise
        await bus.publish("lifecycle.model_deleted", {
            "name": "nonexistent",
            "provider": "LOCAL",
        })
        assert subscriber.sync_count == 1
        await subscriber.stop()


# ---------------------------------------------------------------------------
# Subscription lifecycle
# ---------------------------------------------------------------------------


class TestSubscriptionLifecycle:
    async def test_start_subscribes(self, bus, subscriber):
        assert bus.subscription_count == 0
        await subscriber.start()
        assert bus.subscription_count == 1
        await subscriber.stop()

    async def test_stop_unsubscribes(self, bus, subscriber):
        await subscriber.start()
        assert bus.subscription_count == 1
        await subscriber.stop()
        assert bus.subscription_count == 0

    async def test_events_ignored_after_stop(self, bus, router, subscriber):
        await subscriber.start()
        await bus.publish("lifecycle.model_registered", {
            "name": "before-stop", "provider": "LOCAL", "is_active": True,
        })
        assert router.resolve("before-stop") is not None

        await subscriber.stop()
        await bus.publish("lifecycle.model_registered", {
            "name": "after-stop", "provider": "LOCAL", "is_active": True,
        })
        assert router.resolve("after-stop") is None


# ---------------------------------------------------------------------------
# Full lifecycle flow
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    async def test_register_update_delete_flow(self, bus, router, subscriber):
        await subscriber.start()

        # Register
        await bus.publish("lifecycle.model_registered", {
            "name": "lifecycle-model",
            "provider": "ANTHROPIC",
            "is_active": True,
            "endpoint": "https://api.anthropic.com",
        })
        route = router.resolve("lifecycle-model")
        assert route is not None
        assert route.provider == "anthropic"

        # Update
        await bus.publish("lifecycle.model_updated", {
            "name": "lifecycle-model",
            "provider": "LOCAL",
            "is_active": True,
            "endpoint": "http://localhost:11434",
        })
        route = router.resolve("lifecycle-model")
        assert route.provider == "ollama"
        assert route.upstream_url == "http://localhost:11434"

        # Delete
        await bus.publish("lifecycle.model_deleted", {
            "name": "lifecycle-model",
            "provider": "LOCAL",
        })
        assert router.resolve("lifecycle-model") is None

        assert subscriber.sync_count == 3
        await subscriber.stop()
