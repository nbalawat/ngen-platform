"""Integration tests: model registry and gateway.

Tests model CRUD in the registry and LLM proxying through the gateway
against the real mock-llm backend.
"""

from __future__ import annotations

import uuid

import httpx
import pytest


# ---------------------------------------------------------------------------
# Model Registry CRUD
# ---------------------------------------------------------------------------


class TestModelRegistryCRUD:
    """Full model lifecycle in the registry service."""

    async def test_register_model(self, http: httpx.AsyncClient, registry_url):
        name = f"integ-model-{uuid.uuid4().hex[:8]}"
        resp = await http.post(
            f"{registry_url}/api/v1/models",
            json={
                "name": name,
                "provider": "LOCAL",
                "endpoint": "http://localhost:11434",
                "capabilities": ["STREAMING", "TOOL_USE"],
                "context_window": 128000,
            },
        )
        assert resp.status_code == 201, f"Register failed: {resp.text}"
        data = resp.json()
        assert data["name"] == name
        assert data["provider"] == "LOCAL"
        assert "STREAMING" in data["capabilities"]
        return data

    async def test_list_models(self, http: httpx.AsyncClient, registry_url):
        # Register a model first
        name = f"list-model-{uuid.uuid4().hex[:8]}"
        await http.post(
            f"{registry_url}/api/v1/models",
            json={"name": name, "provider": "LOCAL", "endpoint": "http://x"},
        )
        resp = await http.get(f"{registry_url}/api/v1/models")
        assert resp.status_code == 200
        models = resp.json()
        assert any(m["name"] == name for m in models)

    async def test_get_model_by_name(self, http: httpx.AsyncClient, registry_url):
        name = f"byname-{uuid.uuid4().hex[:8]}"
        await http.post(
            f"{registry_url}/api/v1/models",
            json={"name": name, "provider": "ANTHROPIC", "endpoint": "https://api.anthropic.com"},
        )
        resp = await http.get(f"{registry_url}/api/v1/models/by-name/{name}")
        assert resp.status_code == 200
        assert resp.json()["name"] == name

    async def test_update_model(self, http: httpx.AsyncClient, registry_url):
        name = f"update-model-{uuid.uuid4().hex[:8]}"
        create = await http.post(
            f"{registry_url}/api/v1/models",
            json={"name": name, "provider": "LOCAL", "endpoint": "http://old"},
        )
        model_id = create.json()["id"]

        resp = await http.patch(
            f"{registry_url}/api/v1/models/{model_id}",
            json={"endpoint": "http://new", "context_window": 64000},
        )
        assert resp.status_code == 200
        assert resp.json()["endpoint"] == "http://new"
        assert resp.json()["context_window"] == 64000

    async def test_delete_model(self, http: httpx.AsyncClient, registry_url):
        name = f"delete-model-{uuid.uuid4().hex[:8]}"
        create = await http.post(
            f"{registry_url}/api/v1/models",
            json={"name": name, "provider": "LOCAL", "endpoint": "http://x"},
        )
        model_id = create.json()["id"]

        resp = await http.delete(f"{registry_url}/api/v1/models/{model_id}")
        assert resp.status_code == 204

        # Verify gone
        get_resp = await http.get(f"{registry_url}/api/v1/models/{model_id}")
        assert get_resp.status_code == 404

    async def test_filter_by_provider(self, http: httpx.AsyncClient, registry_url):
        name = f"filter-{uuid.uuid4().hex[:8]}"
        await http.post(
            f"{registry_url}/api/v1/models",
            json={"name": name, "provider": "ANTHROPIC", "endpoint": "https://api.anthropic.com"},
        )
        resp = await http.get(f"{registry_url}/api/v1/models?provider=ANTHROPIC")
        assert resp.status_code == 200
        models = resp.json()
        assert all(m["provider"] == "ANTHROPIC" for m in models)

    async def test_duplicate_name_rejected(self, http: httpx.AsyncClient, registry_url):
        name = f"dup-model-{uuid.uuid4().hex[:8]}"
        await http.post(
            f"{registry_url}/api/v1/models",
            json={"name": name, "provider": "LOCAL", "endpoint": "http://x"},
        )
        resp = await http.post(
            f"{registry_url}/api/v1/models",
            json={"name": name, "provider": "LOCAL", "endpoint": "http://y"},
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Model Gateway — LLM Proxying
# ---------------------------------------------------------------------------


class TestModelGatewayProxy:
    """Test the gateway proxies requests to the mock LLM correctly."""

    async def test_list_gateway_models(self, http: httpx.AsyncClient, gateway_url):
        """Gateway should expose registered models."""
        resp = await http.get(f"{gateway_url}/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert len(data["data"]) > 0

    async def test_chat_completion(self, http: httpx.AsyncClient, gateway_url):
        """Send a chat completion through the gateway to mock-llm."""
        resp = await http.post(
            f"{gateway_url}/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [{"role": "user", "content": "Hello, what is 2+2?"}],
            },
            headers={"x-tenant-id": "integration-test"},
        )
        assert resp.status_code == 200, f"Chat completion failed: {resp.text}"
        data = resp.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert "message" in data["choices"][0]

    async def test_chat_completion_returns_usage(self, http: httpx.AsyncClient, gateway_url):
        """Chat completion should include token usage."""
        resp = await http.post(
            f"{gateway_url}/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [{"role": "user", "content": "Count to five."}],
            },
            headers={"x-tenant-id": "usage-test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "usage" in data
        assert data["usage"]["prompt_tokens"] > 0
        assert data["usage"]["completion_tokens"] > 0

    async def test_rate_limit_headers(self, http: httpx.AsyncClient, gateway_url):
        """Gateway should return rate limit headers."""
        resp = await http.post(
            f"{gateway_url}/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [{"role": "user", "content": "test"}],
            },
            headers={"x-tenant-id": "ratelimit-test"},
        )
        assert resp.status_code == 200
        assert "x-ratelimit-remaining-requests" in resp.headers
        assert "x-ratelimit-remaining-tokens" in resp.headers

    async def test_unknown_model_404(self, http: httpx.AsyncClient, gateway_url):
        """Requesting an unregistered model should return 404."""
        resp = await http.post(
            f"{gateway_url}/v1/chat/completions",
            json={
                "model": "nonexistent-model-xyz",
                "messages": [{"role": "user", "content": "test"}],
            },
        )
        assert resp.status_code == 404

    async def test_tenant_usage_tracking(self, http: httpx.AsyncClient, gateway_url):
        """Gateway should track usage per tenant."""
        tenant = f"usage-{uuid.uuid4().hex[:8]}"

        # Make a request
        await http.post(
            f"{gateway_url}/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [{"role": "user", "content": "track my usage"}],
            },
            headers={"x-tenant-id": tenant},
        )

        # Check usage
        resp = await http.get(f"{gateway_url}/v1/usage/{tenant}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["request_count"] >= 1
        assert data["total_tokens"] > 0

    async def test_multiple_requests_accumulate_usage(self, http: httpx.AsyncClient, gateway_url):
        """Multiple requests should accumulate in usage tracking."""
        tenant = f"accum-{uuid.uuid4().hex[:8]}"

        for _ in range(3):
            await http.post(
                f"{gateway_url}/v1/chat/completions",
                json={
                    "model": "mock-model",
                    "messages": [{"role": "user", "content": "hello"}],
                },
                headers={"x-tenant-id": tenant},
            )

        resp = await http.get(f"{gateway_url}/v1/usage/{tenant}")
        assert resp.json()["request_count"] == 3
