"""Tests for the NGEN SDK MCP client.

Validates the SDK can register servers, discover tools, search tools,
and invoke tools through the real MCP manager service.
"""

from __future__ import annotations


class TestMCPSDK:
    async def test_register_and_list_servers(self, mcp_client):
        client = mcp_client
        server = await client.mcp.register_server({
            "name": "sdk-server",
            "endpoint": "http://sdk-server:3000/mcp",
            "namespace": "sdk-ns",
            "tools": [
                {"name": "sdk-tool", "description": "A test tool", "tags": ["test"]},
            ],
        })
        assert server["name"] == "sdk-server"

        servers = await client.mcp.list_servers(namespace="sdk-ns")
        assert len(servers) == 1

    async def test_get_server(self, mcp_client):
        client = mcp_client
        created = await client.mcp.register_server({
            "name": "get-server",
            "endpoint": "http://get-server:3000/mcp",
            "tools": [],
        })
        server = await client.mcp.get_server(created["id"])
        assert server["name"] == "get-server"

    async def test_delete_server(self, mcp_client):
        client = mcp_client
        created = await client.mcp.register_server({
            "name": "del-server",
            "endpoint": "http://del:3000/mcp",
            "tools": [],
        })
        await client.mcp.delete_server(created["id"])
        servers = await client.mcp.list_servers()
        assert len(servers) == 0

    async def test_list_tools(self, mcp_client):
        client = mcp_client
        await client.mcp.register_server({
            "name": "tool-server",
            "endpoint": "http://tool:3000/mcp",
            "tools": [
                {"name": "search", "description": "Search docs", "tags": ["search"]},
                {"name": "write", "description": "Write docs", "tags": ["write"]},
            ],
        })
        tools = await client.mcp.list_tools(server_name="tool-server")
        assert len(tools) == 2

    async def test_list_tools_by_tag(self, mcp_client):
        client = mcp_client
        await client.mcp.register_server({
            "name": "tagged-server",
            "endpoint": "http://tagged:3000/mcp",
            "tools": [
                {"name": "search", "description": "Search", "tags": ["read"]},
                {"name": "write", "description": "Write", "tags": ["write"]},
            ],
        })
        tools = await client.mcp.list_tools(tag="read")
        assert len(tools) == 1
        assert tools[0]["name"] == "search"

    async def test_search_tools(self, mcp_client):
        client = mcp_client
        await client.mcp.register_server({
            "name": "search-server",
            "endpoint": "http://search:3000/mcp",
            "tools": [
                {"name": "find-docs", "description": "Find documents", "tags": []},
                {"name": "calc", "description": "Calculator", "tags": []},
            ],
        })
        results = await client.mcp.search_tools("find")
        assert len(results) == 1
        assert results[0]["name"] == "find-docs"

    async def test_invoke_tool(self, mcp_client):
        client = mcp_client
        await client.mcp.register_server({
            "name": "invoke-server",
            "endpoint": "http://invoke:3000/mcp",
            "tools": [
                {"name": "hello", "description": "Say hello", "tags": []},
            ],
        })
        result = await client.mcp.invoke(
            "invoke-server", "hello", {"name": "world"}
        )
        assert result["tool_name"] == "hello"
        assert result["result"] is not None
        assert result["error"] is None
