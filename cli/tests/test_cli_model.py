"""Tests for CLI model commands against real in-process model registry."""

from __future__ import annotations


class TestModelRegistry:
    async def test_list_empty(self, registry_client):
        """List models when registry is empty."""
        resp = await registry_client.get("/api/v1/models")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_register_and_list(self, registry_client):
        """Register a model and verify it appears in the list."""
        model_data = {
            "name": "claude-opus",
            "provider": "ANTHROPIC",
            "endpoint": "https://api.anthropic.com/v1/messages",
            "capabilities": ["STREAMING", "TOOL_USE"],
        }
        resp = await registry_client.post("/api/v1/models", json=model_data)
        assert resp.status_code == 201
        created = resp.json()
        assert created["name"] == "claude-opus"

        # List should contain our model
        list_resp = await registry_client.get("/api/v1/models")
        assert list_resp.status_code == 200
        models = list_resp.json()
        assert len(models) == 1
        assert models[0]["name"] == "claude-opus"

    async def test_get_by_name(self, registry_client):
        """Get a model by name."""
        model_data = {
            "name": "test-model",
            "provider": "OPENAI",
            "endpoint": "https://api.openai.com/v1/chat/completions",
            "capabilities": ["STREAMING", "VISION"],
        }
        resp = await registry_client.post("/api/v1/models", json=model_data)
        assert resp.status_code == 201

        resp = await registry_client.get("/api/v1/models/by-name/test-model")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-model"

    async def test_get_not_found(self, registry_client):
        """Get a non-existent model returns 404."""
        resp = await registry_client.get("/api/v1/models/by-name/nonexistent")
        assert resp.status_code == 404

    async def test_delete(self, registry_client):
        """Delete a model."""
        model_data = {
            "name": "delete-me",
            "provider": "LOCAL",
            "endpoint": "http://localhost:11434",
            "capabilities": [],
        }
        created = (await registry_client.post("/api/v1/models", json=model_data)).json()
        model_id = created["id"]

        resp = await registry_client.delete(f"/api/v1/models/{model_id}")
        assert resp.status_code == 204

        # Verify it's gone
        list_resp = await registry_client.get("/api/v1/models")
        names = [m["name"] for m in list_resp.json()]
        assert "delete-me" not in names

    async def test_filter_by_provider(self, registry_client):
        """Filter models by provider."""
        for name, provider, endpoint in [
            ("model-one", "ANTHROPIC", "https://api.anthropic.com"),
            ("model-two", "OPENAI", "https://api.openai.com"),
            ("model-three", "ANTHROPIC", "https://api.anthropic.com"),
        ]:
            await registry_client.post("/api/v1/models", json={
                "name": name, "provider": provider, "endpoint": endpoint,
                "capabilities": [],
            })

        resp = await registry_client.get("/api/v1/models?provider=ANTHROPIC")
        assert resp.status_code == 200
        models = resp.json()
        assert all(m["provider"] == "ANTHROPIC" for m in models)
        assert len(models) == 2
