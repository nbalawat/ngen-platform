"""Integration tests for the model gateway API."""

from __future__ import annotations

import httpx
import pytest


async def test_health(client: httpx.AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


async def test_list_models(client: httpx.AsyncClient):
    resp = await client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    ids = {m["id"] for m in data["data"]}
    assert "mock-model" in ids


class TestProxyChatCompletions:
    async def test_successful_proxy(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [
                    {"role": "user", "content": "Hello"}
                ],
            },
            headers={"x-tenant-id": "tenant-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["choices"][0]["message"]["content"] == "Mock reply."

    async def test_rate_limit_headers(
        self, client: httpx.AsyncClient
    ):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [
                    {"role": "user", "content": "Hi"}
                ],
            },
            headers={"x-tenant-id": "tenant-1"},
        )
        assert "x-ratelimit-remaining-requests" in resp.headers
        assert "x-ratelimit-remaining-tokens" in resp.headers

    async def test_unknown_model_404(
        self, client: httpx.AsyncClient
    ):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "nonexistent",
                "messages": [
                    {"role": "user", "content": "Hi"}
                ],
            },
        )
        assert resp.status_code == 404

    async def test_rate_limit_exceeded(
        self, client: httpx.AsyncClient
    ):
        # RPM is 5 in fixture
        for _ in range(5):
            resp = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "mock-model",
                    "messages": [
                        {"role": "user", "content": "Hi"}
                    ],
                },
                headers={"x-tenant-id": "rate-test"},
            )
            assert resp.status_code == 200

        # 6th request should be rate limited
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [
                    {"role": "user", "content": "Hi"}
                ],
            },
            headers={"x-tenant-id": "rate-test"},
        )
        assert resp.status_code == 429

    async def test_default_tenant(self, client: httpx.AsyncClient):
        """Requests without x-tenant-id use 'default' tenant."""
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [
                    {"role": "user", "content": "Hi"}
                ],
            },
        )
        assert resp.status_code == 200


class TestUsageEndpoint:
    async def test_usage_after_requests(
        self, client: httpx.AsyncClient
    ):
        # Make a request
        await client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [
                    {"role": "user", "content": "Hello world"}
                ],
            },
            headers={"x-tenant-id": "usage-test"},
        )

        resp = await client.get("/v1/usage/usage-test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["request_count"] == 1
        assert data["total_tokens"] > 0

    async def test_usage_empty_tenant(
        self, client: httpx.AsyncClient
    ):
        resp = await client.get("/v1/usage/nobody")
        assert resp.status_code == 200
        data = resp.json()
        assert data["request_count"] == 0
