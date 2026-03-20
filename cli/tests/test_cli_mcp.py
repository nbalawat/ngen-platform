"""Tests for CLI MCP commands against real MCP manager service."""

from __future__ import annotations

import pytest


class TestMCPServerCRUD:
    async def test_register_server(self, mcp_client):
        resp = await mcp_client.post(
            "/api/v1/servers",
            json={
                "name": "test-server",
                "endpoint": "http://localhost:9000/mcp",
                "namespace": "default",
                "transport": "streamable-http",
                "tools": [
                    {
                        "name": "search",
                        "description": "Search documents",
                        "parameters": [
                            {"name": "query", "type": "string", "required": True}
                        ],
                        "tags": ["search", "retrieval"],
                    }
                ],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-server"
        assert data["id"]

    async def test_list_servers(self, mcp_client):
        await mcp_client.post(
            "/api/v1/servers",
            json={
                "name": "server-alpha",
                "endpoint": "http://alpha:9000",
                "tools": [],
            },
        )
        await mcp_client.post(
            "/api/v1/servers",
            json={
                "name": "server-beta",
                "endpoint": "http://beta:9000",
                "tools": [],
            },
        )

        resp = await mcp_client.get("/api/v1/servers")
        assert resp.status_code == 200
        servers = resp.json()
        names = {s["name"] for s in servers}
        assert "server-alpha" in names
        assert "server-beta" in names

    async def test_get_server(self, mcp_client):
        create_resp = await mcp_client.post(
            "/api/v1/servers",
            json={
                "name": "get-test",
                "endpoint": "http://get:9000",
                "tools": [],
            },
        )
        server_id = create_resp.json()["id"]

        resp = await mcp_client.get(f"/api/v1/servers/{server_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "get-test"

    async def test_delete_server(self, mcp_client):
        create_resp = await mcp_client.post(
            "/api/v1/servers",
            json={
                "name": "delete-me",
                "endpoint": "http://del:9000",
                "tools": [],
            },
        )
        server_id = create_resp.json()["id"]

        del_resp = await mcp_client.delete(f"/api/v1/servers/{server_id}")
        assert del_resp.status_code == 204

        get_resp = await mcp_client.get(f"/api/v1/servers/{server_id}")
        assert get_resp.status_code == 404


class TestMCPToolCatalog:
    async def test_list_tools(self, mcp_client):
        await mcp_client.post(
            "/api/v1/servers",
            json={
                "name": "tools-server",
                "endpoint": "http://tools:9000",
                "tools": [
                    {"name": "calc", "description": "Calculator", "tags": ["math"]},
                    {"name": "translate", "description": "Translate text", "tags": ["nlp"]},
                ],
            },
        )

        resp = await mcp_client.get("/api/v1/tools")
        assert resp.status_code == 200
        tools = resp.json()
        tool_names = {t["name"] for t in tools}
        assert "calc" in tool_names
        assert "translate" in tool_names

    async def test_list_tools_by_server(self, mcp_client):
        await mcp_client.post(
            "/api/v1/servers",
            json={
                "name": "srv-a",
                "endpoint": "http://a:9000",
                "tools": [{"name": "tool-a", "description": "A"}],
            },
        )
        await mcp_client.post(
            "/api/v1/servers",
            json={
                "name": "srv-b",
                "endpoint": "http://b:9000",
                "tools": [{"name": "tool-b", "description": "B"}],
            },
        )

        resp = await mcp_client.get("/api/v1/tools", params={"server_name": "srv-a"})
        assert resp.status_code == 200
        tools = resp.json()
        assert all(t["server_name"] == "srv-a" for t in tools)

    async def test_list_tools_by_tag(self, mcp_client):
        await mcp_client.post(
            "/api/v1/servers",
            json={
                "name": "tag-server",
                "endpoint": "http://tags:9000",
                "tools": [
                    {"name": "math-tool", "description": "Math", "tags": ["math"]},
                    {"name": "nlp-tool", "description": "NLP", "tags": ["nlp"]},
                ],
            },
        )

        resp = await mcp_client.get("/api/v1/tools", params={"tag": "math"})
        assert resp.status_code == 200
        tools = resp.json()
        assert all("math" in t.get("tags", []) for t in tools)

    async def test_search_tools(self, mcp_client):
        await mcp_client.post(
            "/api/v1/servers",
            json={
                "name": "search-srv",
                "endpoint": "http://search:9000",
                "tools": [
                    {"name": "document-search", "description": "Search documents by keyword"},
                    {"name": "image-gen", "description": "Generate images from text"},
                ],
            },
        )

        resp = await mcp_client.get("/api/v1/tools/search", params={"q": "document"})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 1
        assert any("document" in r["name"].lower() or "document" in r.get("description", "").lower() for r in results)


class TestMCPToolInvocation:
    async def test_invoke_tool(self, mcp_client):
        await mcp_client.post(
            "/api/v1/servers",
            json={
                "name": "invoke-srv",
                "endpoint": "http://invoke:9000",
                "tools": [
                    {"name": "echo", "description": "Echo input"},
                ],
            },
        )

        resp = await mcp_client.post(
            "/api/v1/invoke",
            json={
                "server_name": "invoke-srv",
                "tool_name": "echo",
                "arguments": {"text": "hello"},
            },
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["server_name"] == "invoke-srv"
        assert result["tool_name"] == "echo"

    async def test_invoke_unknown_server(self, mcp_client):
        resp = await mcp_client.post(
            "/api/v1/invoke",
            json={
                "server_name": "nonexistent",
                "tool_name": "anything",
                "arguments": {},
            },
        )
        assert resp.status_code == 404

    async def test_invoke_unknown_tool(self, mcp_client):
        await mcp_client.post(
            "/api/v1/servers",
            json={
                "name": "real-srv",
                "endpoint": "http://real:9000",
                "tools": [{"name": "real-tool", "description": "exists"}],
            },
        )

        resp = await mcp_client.post(
            "/api/v1/invoke",
            json={
                "server_name": "real-srv",
                "tool_name": "fake-tool",
                "arguments": {},
            },
        )
        assert resp.status_code == 404
