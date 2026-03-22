"""End-to-end tests for built-in tool invocation via the full API pipeline.

Tests the complete flow: seed data → invoke endpoint → builtin handler → result.
Uses the real MCP Manager app with ASGI transport. No mocks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

import mcp_manager.routes as routes
from mcp_manager.app import create_app
from mcp_manager.handlers.knowledge_base import (
    reset_knowledge_base,
    seed_knowledge_base,
)
from mcp_manager.seed import seed_repository


@pytest.fixture()
def e2e_app():
    """Create app with seeded data for end-to-end tests."""
    routes._repository = None
    app = create_app()
    # Manually trigger seed since startup events don't fire in ASGI transport
    repo = routes._get_repository()
    seed_repository(repo)
    return app


@pytest.fixture()
async def client(e2e_app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=e2e_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://mcp-manager"
    ) as c:
        # Trigger KB seed manually
        await seed_knowledge_base()
        yield c


@pytest.fixture(autouse=True)
def _cleanup_kb():
    yield
    reset_knowledge_base()


class TestKnowledgeBaseEndToEnd:
    async def test_invoke_search_docs(self, client):
        """Full pipeline: invoke knowledge-base/search_docs via API."""
        resp = await client.post("/api/v1/invoke", json={
            "server_name": "knowledge-base",
            "tool_name": "search_docs",
            "arguments": {"query": "agent design patterns"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None, f"Unexpected error: {data['error']}"
        assert data["result"] is not None
        assert "Agent Design Patterns" in str(data["result"])

    async def test_invoke_get_document(self, client):
        """Full pipeline: invoke knowledge-base/get_document via API."""
        resp = await client.post("/api/v1/invoke", json={
            "server_name": "knowledge-base",
            "tool_name": "get_document",
            "arguments": {"doc_id": "ngen-architecture"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert "RAPIDS" in str(data["result"])

    async def test_invoke_get_document_not_found(self, client):
        resp = await client.post("/api/v1/invoke", json={
            "server_name": "knowledge-base",
            "tool_name": "get_document",
            "arguments": {"doc_id": "nonexistent"},
        })
        assert resp.status_code == 200
        data = resp.json()
        result_text = str(data.get("result", ""))
        assert "not found" in result_text.lower() or data.get("error") is not None


class TestWebSearchEndToEnd:
    async def test_invoke_web_search(self, client):
        resp = await client.post("/api/v1/invoke", json={
            "server_name": "web-search",
            "tool_name": "search",
            "arguments": {"query": "Python programming", "max_results": 3},
        })
        assert resp.status_code == 200
        data = resp.json()
        if data["error"] is None:
            assert data["result"] is not None

    async def test_invoke_search_missing_query(self, client):
        resp = await client.post("/api/v1/invoke", json={
            "server_name": "web-search",
            "tool_name": "search",
            "arguments": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        result_text = str(data.get("result", ""))
        assert "Missing" in result_text or "Error" in result_text or data.get("error")


class TestBuiltinVsExternalDispatch:
    async def test_builtin_servers_are_marked(self, client):
        resp = await client.get("/api/v1/servers")
        servers = resp.json()
        builtin_names = {
            s["name"] for s in servers if s["transport"] == "builtin"
        }
        assert "web-search" in builtin_names
        assert "knowledge-base" in builtin_names
        assert "document-intelligence" in builtin_names

    async def test_external_servers_remain_streamable(self, client):
        resp = await client.get("/api/v1/servers")
        servers = resp.json()
        builtin_servers = {"web-search", "knowledge-base", "document-intelligence"}
        for s in servers:
            if s["name"] not in builtin_servers:
                assert s["transport"] != "builtin"


class TestDocumentUploadEndToEnd:
    async def test_upload_and_search(self, client):
        """Upload a document, then search for its content."""
        # Upload
        import io
        content = b"Quantum computing uses qubits for parallel processing. " * 20
        files = {"file": ("quantum.txt", io.BytesIO(content), "text/plain")}
        data = {"tenant_id": "test-tenant", "collection": "research"}

        resp = await client.post("/api/v1/documents/upload", files=files, data=data)
        assert resp.status_code == 200
        upload_result = resp.json()
        assert upload_result["status"] == "ready"
        assert upload_result["chunk_count"] > 0

        # List
        resp = await client.get("/api/v1/documents", params={"tenant_id": "test-tenant"})
        assert resp.status_code == 200
        docs = resp.json()
        assert len(docs) >= 1

        # Search via tool invocation
        resp = await client.post("/api/v1/invoke", json={
            "server_name": "knowledge-base",
            "tool_name": "search_docs",
            "arguments": {"query": "quantum computing qubits"},
            "namespace": "test-tenant",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert "quantum" in str(data["result"]).lower()

    async def test_upload_unsupported_format(self, client):
        import io
        files = {"file": ("data.xlsx", io.BytesIO(b"binary"), "application/octet-stream")}
        data = {"tenant_id": "test-tenant", "collection": "docs"}

        resp = await client.post("/api/v1/documents/upload", files=files, data=data)
        assert resp.status_code == 400
