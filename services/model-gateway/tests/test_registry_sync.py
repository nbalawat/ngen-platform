"""Tests for gateway ↔ registry sync.

Uses real model-registry FastAPI app via ASGI transport. No mocks.
"""

from __future__ import annotations

import httpx
import pytest

from model_gateway.registry_sync import RegistrySync, SyncResult
from model_gateway.router import ModelRouter
from model_registry.app import create_app as create_registry_app
from model_registry import routes as registry_routes


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry_app():
    """Fresh model-registry app with reset repository."""
    registry_routes._repository = None
    app = create_registry_app()
    yield app
    registry_routes._repository = None


@pytest.fixture()
def registry_client(registry_app):
    """ASGI transport client for model-registry."""
    transport = httpx.ASGITransport(app=registry_app)
    return httpx.AsyncClient(transport=transport, base_url="http://registry")


@pytest.fixture()
def router():
    """Fresh ModelRouter."""
    return ModelRouter()


@pytest.fixture()
def sync(router, registry_client):
    """RegistrySync wired to real registry via ASGI transport."""
    return RegistrySync(
        router=router,
        registry_url="http://registry",
        http_client=registry_client,
    )


async def _register_model(client: httpx.AsyncClient, name: str, provider: str = "LOCAL", endpoint: str = "http://localhost:11434", **kwargs):
    """Helper to register a model in the registry."""
    body = {
        "name": name,
        "provider": provider,
        "endpoint": endpoint,
        **kwargs,
    }
    resp = await client.post("/api/v1/models", json=body)
    assert resp.status_code == 201, f"Failed to register model: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Basic sync tests
# ---------------------------------------------------------------------------


class TestRegistrySyncBasic:
    """Tests for one-shot sync from registry to gateway."""

    async def test_sync_empty_registry(self, sync):
        result = await sync.sync()
        assert result.success is True
        assert result.models_synced == 0
        assert result.models_added == 0

    async def test_sync_single_model(self, registry_client, sync, router):
        await _register_model(registry_client, "llama3.2", provider="LOCAL")

        result = await sync.sync()
        assert result.success is True
        assert result.models_synced == 1
        assert result.models_added == 1

        # Model should be in the router
        route = router.resolve("llama3.2")
        assert route is not None
        assert route.provider == "ollama"  # LOCAL → ollama
        assert route.upstream_url == "http://localhost:11434"

    async def test_sync_multiple_models(self, registry_client, sync, router):
        await _register_model(registry_client, "llama3.2", provider="LOCAL")
        await _register_model(
            registry_client, "claude-sonnet",
            provider="ANTHROPIC",
            endpoint="https://api.anthropic.com",
        )
        await _register_model(
            registry_client, "gpt-4",
            provider="OPENAI",
            endpoint="https://api.openai.com",
        )

        result = await sync.sync()
        assert result.success is True
        assert result.models_synced == 3
        assert result.models_added == 3

        assert router.resolve("llama3.2").provider == "ollama"
        assert router.resolve("claude-sonnet").provider == "anthropic"
        assert router.resolve("gpt-4").provider == "mock"  # OpenAI maps to mock for now

    async def test_sync_preserves_endpoint(self, registry_client, sync, router):
        await _register_model(
            registry_client, "custom-model",
            provider="ANTHROPIC",
            endpoint="https://custom.endpoint.com/v1",
        )

        await sync.sync()
        route = router.resolve("custom-model")
        assert route.upstream_url == "https://custom.endpoint.com/v1"


# ---------------------------------------------------------------------------
# Idempotent sync tests
# ---------------------------------------------------------------------------


class TestRegistrySyncIdempotent:
    """Tests that repeated syncs are idempotent."""

    async def test_double_sync_no_duplicates(self, registry_client, sync, router):
        await _register_model(registry_client, "model-a", provider="LOCAL")

        r1 = await sync.sync()
        r2 = await sync.sync()

        assert r1.models_added == 1
        assert r2.models_added == 0  # Already exists
        assert r2.models_synced == 1
        assert len(router.list_models()) == 1

    async def test_sync_updates_changed_endpoint(self, registry_client, sync, router):
        model = await _register_model(
            registry_client, "evolving-model",
            provider="LOCAL",
            endpoint="http://old:11434",
        )

        await sync.sync()
        assert router.resolve("evolving-model").upstream_url == "http://old:11434"

        # Update the model endpoint in registry
        model_id = model["id"]
        await registry_client.patch(
            f"/api/v1/models/{model_id}",
            json={"endpoint": "http://new:11434"},
        )

        await sync.sync()
        assert router.resolve("evolving-model").upstream_url == "http://new:11434"


# ---------------------------------------------------------------------------
# Stale model removal
# ---------------------------------------------------------------------------


class TestRegistrySyncRemoval:
    """Tests that removed models are cleaned up from the router."""

    async def test_removes_deleted_models(self, registry_client, sync, router):
        model = await _register_model(registry_client, "temp-model", provider="LOCAL")

        await sync.sync()
        assert router.resolve("temp-model") is not None

        # Delete from registry
        model_id = model["id"]
        resp = await registry_client.delete(f"/api/v1/models/{model_id}")
        assert resp.status_code == 204

        await sync.sync()
        assert router.resolve("temp-model") is None

    async def test_preserves_manually_registered_models(self, registry_client, sync, router):
        # Register a model manually (not via sync)
        router.register("manual-model", "http://manual:8080", provider="mock")

        await _register_model(registry_client, "registry-model", provider="LOCAL")
        await sync.sync()

        # Both should exist
        assert router.resolve("manual-model") is not None
        assert router.resolve("registry-model") is not None

        # Delete registry model
        models = (await registry_client.get("/api/v1/models")).json()
        for m in models:
            await registry_client.delete(f"/api/v1/models/{m['id']}")

        await sync.sync()
        # Manual model survives, registry model removed
        assert router.resolve("manual-model") is not None
        assert router.resolve("registry-model") is None

    async def test_inactive_models_skipped(self, registry_client, sync, router):
        model = await _register_model(registry_client, "active-model", provider="LOCAL")

        await sync.sync()
        assert router.resolve("active-model") is not None

        # Deactivate the model
        await registry_client.patch(
            f"/api/v1/models/{model['id']}",
            json={"is_active": False},
        )

        await sync.sync()
        # Should be removed since it's no longer active
        assert router.resolve("active-model") is None


# ---------------------------------------------------------------------------
# API key propagation
# ---------------------------------------------------------------------------


class TestRegistrySyncAPIKey:
    """Tests that API keys are propagated from registry metadata."""

    async def test_api_key_from_metadata(self, registry_client, sync, router):
        await _register_model(
            registry_client, "keyed-model",
            provider="ANTHROPIC",
            endpoint="https://api.anthropic.com",
            metadata={"api_key": "sk-ant-test-key"},
        )

        await sync.sync()
        route = router.resolve("keyed-model")
        assert route is not None
        assert route.api_key == "sk-ant-test-key"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestRegistrySyncErrors:
    """Tests for sync error handling."""

    async def test_connection_error(self, router):
        """Sync handles unreachable registry gracefully."""
        sync = RegistrySync(
            router=router,
            registry_url="http://nonexistent:9999",
            http_client=httpx.AsyncClient(timeout=1.0),
        )
        result = await sync.sync()
        assert result.success is False
        assert len(result.errors) > 0

    async def test_sync_failure_preserves_existing_routes(self, registry_client, sync, router):
        """Failed sync doesn't remove previously synced models."""
        await _register_model(registry_client, "stable-model", provider="LOCAL")
        await sync.sync()
        assert router.resolve("stable-model") is not None

        # Create a broken sync pointing to nonexistent registry
        broken_sync = RegistrySync(
            router=router,
            registry_url="http://broken:9999",
            http_client=httpx.AsyncClient(timeout=1.0),
        )
        result = await broken_sync.sync()
        assert result.success is False

        # Previous model should still be there
        assert router.resolve("stable-model") is not None


# ---------------------------------------------------------------------------
# SyncResult and metadata
# ---------------------------------------------------------------------------


class TestSyncResult:
    """Tests for sync result tracking."""

    async def test_last_result_stored(self, registry_client, sync):
        assert sync.last_result is None
        await sync.sync()
        assert sync.last_result is not None
        assert sync.last_result.success is True

    async def test_synced_models_tracked(self, registry_client, sync):
        await _register_model(registry_client, "tracked-a", provider="LOCAL")
        await _register_model(registry_client, "tracked-b", provider="LOCAL")
        await sync.sync()
        assert sync.synced_models == {"tracked-a", "tracked-b"}
