"""Tests for MCP tool invocation."""

from __future__ import annotations


class TestToolInvocation:
    async def test_invoke_tool(self, client, knowledge_base_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)

        resp = await client.post("/api/v1/invoke", json={
            "server_name": "knowledge-base",
            "tool_name": "search-docs",
            "arguments": {"query": "quarterly report"},
            "namespace": "acme-corp",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["server_name"] == "knowledge-base"
        assert data["tool_name"] == "search-docs"
        assert data["result"] is not None
        assert data["error"] is None
        assert data["duration_ms"] is not None

    async def test_invoke_server_not_found(self, client):
        resp = await client.post("/api/v1/invoke", json={
            "server_name": "nonexistent",
            "tool_name": "some-tool",
        })
        assert resp.status_code == 404
        assert "nonexistent" in resp.json()["detail"]

    async def test_invoke_tool_not_found(self, client, knowledge_base_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)

        resp = await client.post("/api/v1/invoke", json={
            "server_name": "knowledge-base",
            "tool_name": "nonexistent-tool",
            "namespace": "acme-corp",
        })
        assert resp.status_code == 404
        assert "nonexistent-tool" in resp.json()["detail"]

    async def test_invoke_returns_arguments(self, client, knowledge_base_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)

        resp = await client.post("/api/v1/invoke", json={
            "server_name": "knowledge-base",
            "tool_name": "search-docs",
            "arguments": {"query": "test", "limit": 5},
            "namespace": "acme-corp",
        })
        data = resp.json()
        assert data["result"]["arguments"]["query"] == "test"
        assert data["result"]["arguments"]["limit"] == 5


class TestHealth:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
