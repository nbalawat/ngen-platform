"""Tests for MCP tool invocation via the REST API.

Uses a real mock MCP server (FastAPI) via ASGI transport. No mocks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import mcp_manager.routes as routes
from mcp_manager.app import create_app
from mcp_manager.transport import MCPTransport


# ---------------------------------------------------------------------------
# Mock MCP server — handles JSON-RPC tools/call
# ---------------------------------------------------------------------------


def _create_mock_mcp() -> FastAPI:
    app = FastAPI()

    @app.post("/mcp")
    async def handle(request: Request) -> JSONResponse:
        body = await request.json()
        req_id = body.get("id", "0")
        params = body.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name == "search-docs":
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": f"Results for: {arguments.get('query', '')}"},
                    ],
                },
            })

        if tool_name == "get-document":
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": f"Document {arguments.get('doc_id', 'unknown')}"},
                    ],
                },
            })

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"},
        })

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def _mock_mcp_client() -> AsyncIterator[httpx.AsyncClient]:
    """HTTP client wired to the mock MCP server."""
    transport = httpx.ASGITransport(app=_create_mock_mcp())
    async with httpx.AsyncClient(
        transport=transport, base_url="http://kb-server:3000"
    ) as c:
        yield c


@pytest.fixture()
def mcp_app(_mock_mcp_client) -> FastAPI:
    """MCP Manager app with transport wired to mock MCP server."""
    routes._repository = None
    transport = MCPTransport(client=_mock_mcp_client)
    return create_app(mcp_transport=transport)


@pytest.fixture()
async def client(mcp_app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=mcp_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://mcp-manager"
    ) as c:
        yield c


@pytest.fixture()
def knowledge_base_server():
    return {
        "name": "knowledge-base",
        "description": "Corporate knowledge base MCP server",
        "namespace": "acme-corp",
        "endpoint": "http://kb-server:3000/mcp",
        "transport": "streamable-http",
        "tools": [
            {
                "name": "search-docs",
                "description": "Search documents by query",
                "parameters": [
                    {"name": "query", "type": "string", "required": True},
                    {"name": "limit", "type": "integer", "required": False},
                ],
                "tags": ["search", "documents"],
            },
            {
                "name": "get-document",
                "description": "Get a document by ID",
                "parameters": [
                    {"name": "doc_id", "type": "string", "required": True},
                ],
                "tags": ["documents"],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


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
        # Real result from mock MCP server
        assert "quarterly report" in data["result"]["text"]

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

    async def test_invoke_returns_content(self, client, knowledge_base_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)

        resp = await client.post("/api/v1/invoke", json={
            "server_name": "knowledge-base",
            "tool_name": "search-docs",
            "arguments": {"query": "test", "limit": 5},
            "namespace": "acme-corp",
        })
        data = resp.json()
        # Content blocks from JSON-RPC response
        assert "content" in data["result"]
        assert len(data["result"]["content"]) > 0

    async def test_invoke_different_tool(self, client, knowledge_base_server):
        await client.post("/api/v1/servers", json=knowledge_base_server)

        resp = await client.post("/api/v1/invoke", json={
            "server_name": "knowledge-base",
            "tool_name": "get-document",
            "arguments": {"doc_id": "DOC-123"},
            "namespace": "acme-corp",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "DOC-123" in data["result"]["text"]


class TestHealth:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
