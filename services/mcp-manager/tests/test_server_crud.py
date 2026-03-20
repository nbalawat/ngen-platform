"""Tests for MCP server registration and CRUD operations."""

from __future__ import annotations


class TestServerRegistration:
    async def test_register_server(self, client, knowledge_base_server):
        resp = await client.post("/api/v1/servers", json=knowledge_base_server)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "knowledge-base"
        assert data["namespace"] == "acme-corp"
        assert data["endpoint"] == "http://kb-server:3000/mcp"
        assert data["transport"] == "streamable-http"
        assert data["status"] == "registered"
        assert len(data["tools"]) == 2
        assert "id" in data

    async def test_register_with_auth(self, client, knowledge_base_server):
        resp = await client.post("/api/v1/servers", json=knowledge_base_server)
        assert resp.status_code == 201
        data = resp.json()
        assert data["auth"]["type"] == "api-key"
        assert data["auth"]["secret_ref"] == "kb-api-key"

    async def test_duplicate_name_returns_409(self, client, knowledge_base_server):
        resp1 = await client.post("/api/v1/servers", json=knowledge_base_server)
        assert resp1.status_code == 201
        resp2 = await client.post("/api/v1/servers", json=knowledge_base_server)
        assert resp2.status_code == 409

    async def test_duplicate_name_different_namespace_ok(self, client):
        base = {
            "name": "shared-server",
            "endpoint": "http://server:3000/mcp",
            "tools": [],
        }
        resp1 = await client.post("/api/v1/servers", json={**base, "namespace": "ns-a"})
        assert resp1.status_code == 201
        resp2 = await client.post("/api/v1/servers", json={**base, "namespace": "ns-b"})
        assert resp2.status_code == 201

    async def test_register_minimal_server(self, client):
        resp = await client.post("/api/v1/servers", json={
            "name": "minimal-server",
            "endpoint": "http://server:3000/mcp",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["auth"]["type"] == "none"
        assert data["transport"] == "streamable-http"
        assert data["tools"] == []


class TestServerRead:
    async def test_list_empty(self, client):
        resp = await client.get("/api/v1/servers")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_namespace_filter(
        self, client, knowledge_base_server, database_server
    ):
        await client.post("/api/v1/servers", json=knowledge_base_server)
        await client.post("/api/v1/servers", json={
            "name": "other-server",
            "namespace": "other-ns",
            "endpoint": "http://other:3000/mcp",
        })
        resp = await client.get("/api/v1/servers?namespace=acme-corp")
        assert resp.status_code == 200
        servers = resp.json()
        assert len(servers) == 1
        assert servers[0]["name"] == "knowledge-base"

    async def test_get_by_id(self, client, knowledge_base_server):
        created = (await client.post("/api/v1/servers", json=knowledge_base_server)).json()
        resp = await client.get(f"/api/v1/servers/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "knowledge-base"

    async def test_get_not_found(self, client):
        resp = await client.get("/api/v1/servers/nonexistent")
        assert resp.status_code == 404

    async def test_get_by_name(self, client, knowledge_base_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)
        resp = await client.get(
            "/api/v1/servers/by-name/knowledge-base?namespace=acme-corp"
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "knowledge-base"

    async def test_get_by_name_not_found(self, client):
        resp = await client.get("/api/v1/servers/by-name/nope")
        assert resp.status_code == 404


class TestServerUpdate:
    async def test_update_endpoint(self, client, knowledge_base_server):
        created = (await client.post("/api/v1/servers", json=knowledge_base_server)).json()
        resp = await client.patch(f"/api/v1/servers/{created['id']}", json={
            "endpoint": "http://new-kb-server:3000/mcp",
        })
        assert resp.status_code == 200
        assert resp.json()["endpoint"] == "http://new-kb-server:3000/mcp"

    async def test_update_status(self, client, knowledge_base_server):
        created = (await client.post("/api/v1/servers", json=knowledge_base_server)).json()
        resp = await client.patch(f"/api/v1/servers/{created['id']}", json={
            "status": "healthy",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    async def test_update_not_found(self, client):
        resp = await client.patch("/api/v1/servers/bad-id", json={"status": "offline"})
        assert resp.status_code == 404

    async def test_update_tools_rebuilds_catalog(self, client, knowledge_base_server):
        created = (await client.post("/api/v1/servers", json=knowledge_base_server)).json()

        # Initially has 2 tools
        tools_resp = await client.get("/api/v1/tools?server_name=knowledge-base")
        assert len(tools_resp.json()) == 2

        # Update to 1 tool
        await client.patch(f"/api/v1/servers/{created['id']}", json={
            "tools": [
                {"name": "new-tool", "description": "A new tool", "tags": ["new"]},
            ],
        })

        tools_resp = await client.get("/api/v1/tools?server_name=knowledge-base")
        assert len(tools_resp.json()) == 1
        assert tools_resp.json()[0]["name"] == "new-tool"


class TestServerDelete:
    async def test_delete(self, client, knowledge_base_server):
        created = (await client.post("/api/v1/servers", json=knowledge_base_server)).json()
        resp = await client.delete(f"/api/v1/servers/{created['id']}")
        assert resp.status_code == 204

        get_resp = await client.get(f"/api/v1/servers/{created['id']}")
        assert get_resp.status_code == 404

    async def test_delete_removes_tools(self, client, knowledge_base_server):
        created = (await client.post("/api/v1/servers", json=knowledge_base_server)).json()

        tools_before = await client.get("/api/v1/tools")
        assert len(tools_before.json()) == 2

        await client.delete(f"/api/v1/servers/{created['id']}")

        tools_after = await client.get("/api/v1/tools")
        assert len(tools_after.json()) == 0

    async def test_delete_not_found(self, client):
        resp = await client.delete("/api/v1/servers/bad-id")
        assert resp.status_code == 404
