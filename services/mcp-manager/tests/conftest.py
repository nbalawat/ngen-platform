"""Shared fixtures for MCP Manager tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

import mcp_manager.routes as routes
from mcp_manager.app import create_app


@pytest.fixture()
def mcp_app():
    """Create a fresh MCP Manager app with clean state."""
    routes._repository = None
    return create_app()


@pytest.fixture()
async def client(mcp_app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=mcp_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://mcp-manager"
    ) as c:
        yield c


# -----------------------------------------------------------------------
# Reusable server payloads
# -----------------------------------------------------------------------


@pytest.fixture()
def knowledge_base_server():
    return {
        "name": "knowledge-base",
        "description": "Corporate knowledge base MCP server",
        "namespace": "acme-corp",
        "endpoint": "http://kb-server:3000/mcp",
        "transport": "streamable-http",
        "auth": {"type": "api-key", "secret_ref": "kb-api-key"},
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
        "health_check_path": "/health",
    }


@pytest.fixture()
def database_server():
    return {
        "name": "analytics-db",
        "description": "Analytics database MCP server",
        "namespace": "acme-corp",
        "endpoint": "http://db-server:3001/mcp",
        "transport": "streamable-http",
        "auth": {"type": "oauth2", "config": {"scope": "read"}},
        "tools": [
            {
                "name": "run-query",
                "description": "Execute a SQL query",
                "parameters": [
                    {"name": "sql", "type": "string", "required": True},
                ],
                "tags": ["database", "sql"],
            },
        ],
    }
