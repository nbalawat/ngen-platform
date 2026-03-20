from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


async def test_health_check(client: httpx.AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"


# ---------------------------------------------------------------------------
# Model CRUD
# ---------------------------------------------------------------------------


class TestModelEndpoints:
    async def test_register_model(
        self,
        client: httpx.AsyncClient,
        sample_model_payload: dict[str, Any],
    ):
        resp = await client.post("/api/v1/models", json=sample_model_payload)
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert "created_at" in body
        assert "updated_at" in body
        assert body["name"] == sample_model_payload["name"]
        assert body["provider"] == sample_model_payload["provider"]

    async def test_register_duplicate_name(
        self,
        client: httpx.AsyncClient,
        sample_model_payload: dict[str, Any],
    ):
        resp1 = await client.post("/api/v1/models", json=sample_model_payload)
        assert resp1.status_code == 201

        resp2 = await client.post("/api/v1/models", json=sample_model_payload)
        assert resp2.status_code == 409

    async def test_list_models(
        self,
        client: httpx.AsyncClient,
        sample_model_payload: dict[str, Any],
    ):
        await client.post("/api/v1/models", json=sample_model_payload)
        resp = await client.get("/api/v1/models")
        assert resp.status_code == 200
        items = resp.json()
        assert isinstance(items, list)
        assert len(items) >= 1

    async def test_list_models_filter_by_provider(
        self,
        client: httpx.AsyncClient,
        sample_model_payload: dict[str, Any],
    ):
        # Create an ANTHROPIC model
        await client.post("/api/v1/models", json=sample_model_payload)

        # Create an OPENAI model
        openai_payload = {
            **sample_model_payload,
            "name": "gpt-4o",
            "provider": "OPENAI",
            "endpoint": "https://api.openai.com/v1/chat/completions",
        }
        await client.post("/api/v1/models", json=openai_payload)

        # Filter by ANTHROPIC
        resp = await client.get("/api/v1/models?provider=ANTHROPIC")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["provider"] == "ANTHROPIC"

        # Filter by OPENAI
        resp = await client.get("/api/v1/models?provider=OPENAI")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["provider"] == "OPENAI"

    async def test_get_model_by_id(
        self,
        client: httpx.AsyncClient,
        sample_model_payload: dict[str, Any],
    ):
        create_resp = await client.post(
            "/api/v1/models", json=sample_model_payload
        )
        model_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/models/{model_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == model_id

    async def test_get_model_not_found(self, client: httpx.AsyncClient):
        fake_id = str(uuid4())
        resp = await client.get(f"/api/v1/models/{fake_id}")
        assert resp.status_code == 404

    async def test_get_model_by_name(
        self,
        client: httpx.AsyncClient,
        sample_model_payload: dict[str, Any],
    ):
        await client.post("/api/v1/models", json=sample_model_payload)
        name = sample_model_payload["name"]

        resp = await client.get(f"/api/v1/models/by-name/{name}")
        assert resp.status_code == 200
        assert resp.json()["name"] == name

    async def test_get_model_by_name_not_found(
        self, client: httpx.AsyncClient
    ):
        resp = await client.get("/api/v1/models/by-name/nonexistent")
        assert resp.status_code == 404

    async def test_update_model(
        self,
        client: httpx.AsyncClient,
        sample_model_payload: dict[str, Any],
    ):
        create_resp = await client.post(
            "/api/v1/models", json=sample_model_payload
        )
        model_id = create_resp.json()["id"]

        patch_resp = await client.patch(
            f"/api/v1/models/{model_id}",
            json={"is_active": False, "max_output_tokens": 8000},
        )
        assert patch_resp.status_code == 200
        body = patch_resp.json()
        assert body["is_active"] is False
        assert body["max_output_tokens"] == 8000

    async def test_update_model_not_found(self, client: httpx.AsyncClient):
        fake_id = str(uuid4())
        resp = await client.patch(
            f"/api/v1/models/{fake_id}",
            json={"is_active": False},
        )
        assert resp.status_code == 404

    async def test_update_model_duplicate_name(
        self,
        client: httpx.AsyncClient,
        sample_model_payload: dict[str, Any],
    ):
        # Create two models
        await client.post("/api/v1/models", json=sample_model_payload)
        second_payload = {
            **sample_model_payload,
            "name": "second-model",
        }
        resp2 = await client.post("/api/v1/models", json=second_payload)
        second_id = resp2.json()["id"]

        # Try to rename second to first's name
        patch_resp = await client.patch(
            f"/api/v1/models/{second_id}",
            json={"name": sample_model_payload["name"]},
        )
        assert patch_resp.status_code == 409

    async def test_delete_model(
        self,
        client: httpx.AsyncClient,
        sample_model_payload: dict[str, Any],
    ):
        create_resp = await client.post(
            "/api/v1/models", json=sample_model_payload
        )
        model_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/api/v1/models/{model_id}")
        assert del_resp.status_code == 204

        get_resp = await client.get(f"/api/v1/models/{model_id}")
        assert get_resp.status_code == 404

    async def test_delete_model_not_found(self, client: httpx.AsyncClient):
        fake_id = str(uuid4())
        resp = await client.delete(f"/api/v1/models/{fake_id}")
        assert resp.status_code == 404
