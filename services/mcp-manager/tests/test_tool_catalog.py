"""Tests for MCP tool catalog operations."""

from __future__ import annotations


class TestToolListing:
    async def test_list_all_tools(self, client, knowledge_base_server, database_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)
        await client.post("/api/v1/servers", json=database_server)

        resp = await client.get("/api/v1/tools")
        assert resp.status_code == 200
        tools = resp.json()
        assert len(tools) == 3  # 2 from kb + 1 from db

    async def test_filter_by_server_name(self, client, knowledge_base_server, database_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)
        await client.post("/api/v1/servers", json=database_server)

        resp = await client.get("/api/v1/tools?server_name=knowledge-base")
        tools = resp.json()
        assert len(tools) == 2
        assert all(t["server_name"] == "knowledge-base" for t in tools)

    async def test_filter_by_tag(self, client, knowledge_base_server, database_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)
        await client.post("/api/v1/servers", json=database_server)

        resp = await client.get("/api/v1/tools?tag=documents")
        tools = resp.json()
        assert len(tools) == 2  # search-docs and get-document both tagged "documents"

    async def test_filter_by_database_tag(self, client, knowledge_base_server, database_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)
        await client.post("/api/v1/servers", json=database_server)

        resp = await client.get("/api/v1/tools?tag=database")
        tools = resp.json()
        assert len(tools) == 1
        assert tools[0]["name"] == "run-query"

    async def test_get_tool_by_id(self, client, knowledge_base_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)

        all_tools = (await client.get("/api/v1/tools")).json()
        tool_id = all_tools[0]["id"]

        resp = await client.get(f"/api/v1/tools/{tool_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == tool_id

    async def test_get_tool_not_found(self, client):
        resp = await client.get("/api/v1/tools/nonexistent")
        assert resp.status_code == 404


class TestToolSearch:
    async def test_search_by_name(self, client, knowledge_base_server, database_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)
        await client.post("/api/v1/servers", json=database_server)

        resp = await client.get("/api/v1/tools/search?q=search")
        tools = resp.json()
        assert len(tools) == 1
        assert tools[0]["name"] == "search-docs"

    async def test_search_by_description(self, client, knowledge_base_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)

        resp = await client.get("/api/v1/tools/search?q=document")
        tools = resp.json()
        assert len(tools) == 2  # Both kb tools mention "document" in description

    async def test_search_by_tag(self, client, database_server):
        await client.post("/api/v1/servers", json=database_server)

        resp = await client.get("/api/v1/tools/search?q=sql")
        tools = resp.json()
        assert len(tools) == 1
        assert tools[0]["name"] == "run-query"

    async def test_search_no_results(self, client, knowledge_base_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)

        resp = await client.get("/api/v1/tools/search?q=nonexistent")
        assert resp.json() == []

    async def test_search_case_insensitive(self, client, knowledge_base_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)

        resp = await client.get("/api/v1/tools/search?q=SEARCH")
        tools = resp.json()
        assert len(tools) == 1


class TestToolParameters:
    async def test_tool_parameters_preserved(self, client, knowledge_base_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)

        tools = (await client.get("/api/v1/tools?server_name=knowledge-base")).json()
        search_tool = next(t for t in tools if t["name"] == "search-docs")

        assert len(search_tool["parameters"]) == 2
        query_param = next(p for p in search_tool["parameters"] if p["name"] == "query")
        assert query_param["type"] == "string"
        assert query_param["required"] is True
