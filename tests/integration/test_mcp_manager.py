"""Integration tests: MCP Manager — server registration, tool catalog, invocation.

Tests the full MCP lifecycle against the real containerized service.
"""

from __future__ import annotations

import uuid

import httpx
import pytest


# ---------------------------------------------------------------------------
# Server Registration
# ---------------------------------------------------------------------------


class TestMCPServerRegistration:
    """MCP server CRUD lifecycle."""

    async def test_register_server(self, http: httpx.AsyncClient, mcp_url):
        name = f"integ-server-{uuid.uuid4().hex[:8]}"
        resp = await http.post(
            f"{mcp_url}/api/v1/servers",
            json={
                "name": name,
                "namespace": "integration-test",
                "endpoint": "http://example.com:8080/mcp",
                "transport": "stdio",
                "tools": [
                    {
                        "name": "read_file",
                        "description": "Read contents of a file",
                        "parameters": [
                            {"name": "path", "type": "string", "required": True}
                        ],
                        "tags": ["filesystem", "read"],
                    },
                    {
                        "name": "write_file",
                        "description": "Write contents to a file",
                        "parameters": [
                            {"name": "path", "type": "string", "required": True},
                            {"name": "content", "type": "string", "required": True},
                        ],
                        "tags": ["filesystem", "write"],
                    },
                ],
            },
        )
        assert resp.status_code == 201, f"Register server failed: {resp.text}"
        data = resp.json()
        assert data["name"] == name
        assert len(data["tools"]) == 2

    async def test_list_servers(self, http: httpx.AsyncClient, mcp_url):
        resp = await http.get(f"{mcp_url}/api/v1/servers")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_server(self, http: httpx.AsyncClient, mcp_url):
        name = f"get-server-{uuid.uuid4().hex[:8]}"
        create = await http.post(
            f"{mcp_url}/api/v1/servers",
            json={
                "name": name,
                "namespace": "default",
                "endpoint": "http://example.com/mcp",
                "transport": "streamable-http",
                "tools": [],
            },
        )
        server_id = create.json()["id"]

        resp = await http.get(f"{mcp_url}/api/v1/servers/{server_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == name

    async def test_delete_server(self, http: httpx.AsyncClient, mcp_url):
        name = f"del-server-{uuid.uuid4().hex[:8]}"
        create = await http.post(
            f"{mcp_url}/api/v1/servers",
            json={
                "name": name,
                "namespace": "default",
                "endpoint": "http://example.com/mcp",
                "transport": "stdio",
                "tools": [],
            },
        )
        server_id = create.json()["id"]

        resp = await http.delete(f"{mcp_url}/api/v1/servers/{server_id}")
        assert resp.status_code == 204

        get_resp = await http.get(f"{mcp_url}/api/v1/servers/{server_id}")
        assert get_resp.status_code == 404

    async def test_duplicate_server_rejected(self, http: httpx.AsyncClient, mcp_url):
        name = f"dup-server-{uuid.uuid4().hex[:8]}"
        ns = f"dup-ns-{uuid.uuid4().hex[:8]}"
        await http.post(
            f"{mcp_url}/api/v1/servers",
            json={
                "name": name,
                "namespace": ns,
                "endpoint": "http://a.com/mcp",
                "transport": "stdio",
                "tools": [],
            },
        )
        resp = await http.post(
            f"{mcp_url}/api/v1/servers",
            json={
                "name": name,
                "namespace": ns,
                "endpoint": "http://b.com/mcp",
                "transport": "stdio",
                "tools": [],
            },
        )
        assert resp.status_code == 409

    async def test_update_server(self, http: httpx.AsyncClient, mcp_url):
        name = f"upd-server-{uuid.uuid4().hex[:8]}"
        create = await http.post(
            f"{mcp_url}/api/v1/servers",
            json={
                "name": name,
                "namespace": "default",
                "endpoint": "http://old.com/mcp",
                "transport": "stdio",
                "tools": [],
            },
        )
        server_id = create.json()["id"]

        resp = await http.patch(
            f"{mcp_url}/api/v1/servers/{server_id}",
            json={"endpoint": "http://new.com/mcp", "description": "Updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["endpoint"] == "http://new.com/mcp"
        assert resp.json()["description"] == "Updated"


# ---------------------------------------------------------------------------
# Tool Catalog
# ---------------------------------------------------------------------------


class TestMCPToolCatalog:
    """Tool discovery and search across registered servers."""

    async def _register_with_tools(self, http, mcp_url, name_suffix=""):
        """Helper to register a server with tools."""
        name = f"tools-server-{name_suffix or uuid.uuid4().hex[:8]}"
        ns = f"tools-ns-{uuid.uuid4().hex[:8]}"
        await http.post(
            f"{mcp_url}/api/v1/servers",
            json={
                "name": name,
                "namespace": ns,
                "endpoint": "http://tool-server.example.com/mcp",
                "transport": "stdio",
                "tools": [
                    {
                        "name": "web_search",
                        "description": "Search the web for information",
                        "parameters": [{"name": "query", "type": "string", "required": True}],
                        "tags": ["search", "web"],
                    },
                    {
                        "name": "sql_query",
                        "description": "Execute a SQL query against the database",
                        "parameters": [
                            {"name": "query", "type": "string", "required": True},
                            {"name": "database", "type": "string", "required": False},
                        ],
                        "tags": ["database", "sql"],
                    },
                ],
            },
        )
        return name, ns

    async def test_list_tools(self, http: httpx.AsyncClient, mcp_url):
        await self._register_with_tools(http, mcp_url)
        resp = await http.get(f"{mcp_url}/api/v1/tools")
        assert resp.status_code == 200
        tools = resp.json()
        assert len(tools) > 0

    async def test_search_tools_by_name(self, http: httpx.AsyncClient, mcp_url):
        await self._register_with_tools(http, mcp_url)
        resp = await http.get(f"{mcp_url}/api/v1/tools/search?q=web_search")
        assert resp.status_code == 200
        tools = resp.json()
        assert any("web_search" in t["name"] for t in tools)

    async def test_search_tools_by_description(self, http: httpx.AsyncClient, mcp_url):
        await self._register_with_tools(http, mcp_url)
        resp = await http.get(f"{mcp_url}/api/v1/tools/search?q=SQL")
        assert resp.status_code == 200
        tools = resp.json()
        assert len(tools) > 0

    async def test_filter_tools_by_tag(self, http: httpx.AsyncClient, mcp_url):
        await self._register_with_tools(http, mcp_url)
        resp = await http.get(f"{mcp_url}/api/v1/tools?tag=database")
        assert resp.status_code == 200
        tools = resp.json()
        assert all(any("database" in t.get("tags", []) for t in [tool]) for tool in tools)


# ---------------------------------------------------------------------------
# Tool Invocation (stub)
# ---------------------------------------------------------------------------


class TestMCPToolInvocation:
    """Test tool invocation endpoint (returns stub response)."""

    async def test_invoke_tool(self, http: httpx.AsyncClient, mcp_url):
        name = f"invoke-server-{uuid.uuid4().hex[:8]}"
        ns = f"invoke-ns-{uuid.uuid4().hex[:8]}"
        await http.post(
            f"{mcp_url}/api/v1/servers",
            json={
                "name": name,
                "namespace": ns,
                "endpoint": "http://invoke.example.com/mcp",
                "transport": "stdio",
                "tools": [
                    {
                        "name": "calculator",
                        "description": "Do math",
                        "parameters": [{"name": "expression", "type": "string", "required": True}],
                    },
                ],
            },
        )

        resp = await http.post(
            f"{mcp_url}/api/v1/invoke",
            json={
                "server_name": name,
                "tool_name": "calculator",
                "arguments": {"expression": "2 + 2"},
                "namespace": ns,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data or "error" in data

    async def test_invoke_nonexistent_server(self, http: httpx.AsyncClient, mcp_url):
        resp = await http.post(
            f"{mcp_url}/api/v1/invoke",
            json={
                "server_name": "nonexistent-server-xyz",
                "tool_name": "any",
                "arguments": {},
                "namespace": "default",
            },
        )
        assert resp.status_code == 404
