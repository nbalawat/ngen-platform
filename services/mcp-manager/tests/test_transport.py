"""Tests for MCPTransport — real HTTP transport for MCP tool invocation.

Uses a real FastAPI mock MCP server via ASGI transport. No mocks.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mcp_manager.models import (
    AuthConfig,
    AuthType,
    Server,
    ServerStatus,
    ToolDefinition,
    ToolParameter,
    TransportType,
)
from mcp_manager.transport import MCPTransport, MCPTransportError


# ---------------------------------------------------------------------------
# Mock MCP server — a real FastAPI app that implements JSON-RPC
# ---------------------------------------------------------------------------


def create_mock_mcp_server() -> FastAPI:
    """Create a mock MCP server implementing JSON-RPC tools/call."""
    app = FastAPI()

    @app.post("/mcp")
    async def handle_jsonrpc(request: Request) -> JSONResponse:
        body = await request.json()
        method = body.get("method", "")
        req_id = body.get("id", "0")
        params = body.get("params", {})

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})

            if tool_name == "search-docs":
                query = arguments.get("query", "")
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": f"Found 3 results for '{query}'"},
                            {"type": "text", "text": "1. Document A\n2. Document B\n3. Document C"},
                        ],
                    },
                })

            if tool_name == "calculate":
                a = arguments.get("a", 0)
                b = arguments.get("b", 0)
                op = arguments.get("op", "add")
                result = a + b if op == "add" else a - b
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": str(result)},
                        ],
                    },
                })

            if tool_name == "error-tool":
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32000,
                        "message": "Tool execution failed: internal error",
                    },
                })

            if tool_name == "empty-result":
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {},
                })

            if tool_name == "raw-result":
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"value": 42, "status": "ok"},
                })

            # Unknown tool
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Tool '{tool_name}' not found",
                },
            })

        return JSONResponse(
            {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}},
        )

    @app.post("/mcp-auth")
    async def handle_auth(request: Request) -> JSONResponse:
        """Endpoint that requires auth header."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(
                {"error": "Unauthorized"},
                status_code=401,
            )

        body = await request.json()
        req_id = body.get("id", "0")
        params = body.get("params", {})

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {"type": "text", "text": f"Authenticated: {auth}"},
                ],
            },
        })

    @app.post("/mcp-500")
    async def handle_500(request: Request) -> JSONResponse:
        return JSONResponse(
            {"error": "Internal server error"},
            status_code=500,
        )

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_mcp_app() -> FastAPI:
    return create_mock_mcp_server()


@pytest.fixture()
async def mcp_client(mock_mcp_app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=mock_mcp_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://mcp-server"
    ) as c:
        yield c


@pytest.fixture()
def transport(mcp_client) -> MCPTransport:
    return MCPTransport(client=mcp_client)


def _make_server(
    name: str = "test-server",
    endpoint: str = "http://mcp-server/mcp",
    transport_type: TransportType = TransportType.STREAMABLE_HTTP,
    auth: AuthConfig | None = None,
) -> Server:
    return Server(
        name=name,
        endpoint=endpoint,
        transport=transport_type,
        auth=auth or AuthConfig(),
        tools=[
            ToolDefinition(
                name="search-docs",
                description="Search documents",
                parameters=[ToolParameter(name="query", type="string", required=True)],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Successful invocations
# ---------------------------------------------------------------------------


class TestSuccessfulInvocation:
    async def test_invoke_search_tool(self, transport):
        server = _make_server()
        result = await transport.invoke(server, "search-docs", {"query": "hello"})

        assert "content" in result
        assert "text" in result
        assert "hello" in result["text"]

    async def test_invoke_calculator(self, transport):
        server = _make_server()
        result = await transport.invoke(server, "calculate", {"a": 10, "b": 5, "op": "add"})

        assert result["text"] == "15"

    async def test_invoke_subtraction(self, transport):
        server = _make_server()
        result = await transport.invoke(server, "calculate", {"a": 10, "b": 3, "op": "sub"})

        assert result["text"] == "7"

    async def test_content_blocks_preserved(self, transport):
        server = _make_server()
        result = await transport.invoke(server, "search-docs", {"query": "test"})

        assert len(result["content"]) == 2
        assert result["content"][0]["type"] == "text"
        assert result["content"][1]["type"] == "text"

    async def test_raw_result_passthrough(self, transport):
        """Non-content results are passed through as-is."""
        server = _make_server()
        result = await transport.invoke(server, "raw-result", {})

        assert result["value"] == 42
        assert result["status"] == "ok"

    async def test_empty_result(self, transport):
        server = _make_server()
        result = await transport.invoke(server, "empty-result", {})
        assert result == {}


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    async def test_jsonrpc_error_raises(self, transport):
        server = _make_server()
        with pytest.raises(MCPTransportError, match="Tool execution failed"):
            await transport.invoke(server, "error-tool", {})

    async def test_unknown_tool_raises(self, transport):
        server = _make_server()
        with pytest.raises(MCPTransportError, match="not found"):
            await transport.invoke(server, "nonexistent-tool", {})

    async def test_http_500_raises(self, transport):
        server = _make_server(endpoint="http://mcp-server/mcp-500")
        with pytest.raises(MCPTransportError, match="500"):
            await transport.invoke(server, "any-tool", {})

    async def test_connection_refused_raises(self):
        transport = MCPTransport(timeout=2.0)
        server = _make_server(endpoint="http://127.0.0.1:19999/mcp")
        with pytest.raises(MCPTransportError, match="Connection failed"):
            await transport.invoke(server, "any-tool", {})

    async def test_unsupported_transport_raises(self, transport):
        server = _make_server(transport_type=TransportType.STDIO)
        with pytest.raises(MCPTransportError, match="not supported"):
            await transport.invoke(server, "any-tool", {})


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestAuthentication:
    async def test_api_key_auth(self, transport):
        server = _make_server(
            endpoint="http://mcp-server/mcp-auth",
            auth=AuthConfig(type=AuthType.API_KEY, secret_ref="test-secret-key"),
        )
        result = await transport.invoke(server, "any-tool", {})
        assert "Bearer test-secret-key" in result["text"]

    async def test_oauth2_auth(self, transport):
        server = _make_server(
            endpoint="http://mcp-server/mcp-auth",
            auth=AuthConfig(
                type=AuthType.OAUTH2,
                config={"access_token": "oauth-token-xyz"},
            ),
        )
        result = await transport.invoke(server, "any-tool", {})
        assert "Bearer oauth-token-xyz" in result["text"]

    async def test_no_auth(self, transport):
        server = _make_server(
            endpoint="http://mcp-server/mcp-auth",
            auth=AuthConfig(type=AuthType.NONE),
        )
        with pytest.raises(MCPTransportError, match="401"):
            await transport.invoke(server, "any-tool", {})

    async def test_api_key_from_config(self, transport):
        server = _make_server(
            endpoint="http://mcp-server/mcp-auth",
            auth=AuthConfig(
                type=AuthType.API_KEY,
                config={"api_key": "config-key"},
            ),
        )
        result = await transport.invoke(server, "any-tool", {})
        assert "Bearer config-key" in result["text"]


# ---------------------------------------------------------------------------
# SSE transport (uses same HTTP path)
# ---------------------------------------------------------------------------


class TestSSETransport:
    async def test_sse_transport_works(self, transport):
        """SSE transport should use the same HTTP invocation path."""
        server = _make_server(transport_type=TransportType.SSE)
        result = await transport.invoke(server, "search-docs", {"query": "sse-test"})
        assert "sse-test" in result["text"]
