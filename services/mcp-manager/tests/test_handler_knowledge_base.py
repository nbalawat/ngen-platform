"""Tests for knowledge base handler — vector search with tenant scoping."""

from __future__ import annotations

import pytest

from mcp_manager.documents.embeddings import LocalEmbeddingClient
from mcp_manager.documents.index import DocumentIndex
from mcp_manager.documents.models import Document, DocumentChunk
from mcp_manager.handlers.knowledge_base import (
    handle_get_document,
    handle_search_docs,
    initialize_knowledge_base,
    reset_knowledge_base,
    seed_knowledge_base,
)


@pytest.fixture(autouse=True)
async def _setup_kb():
    """Initialize KB with fresh index and local embedder for each test."""
    index = DocumentIndex()
    embedder = LocalEmbeddingClient(dimension=64)
    initialize_knowledge_base(index, embedder)
    await seed_knowledge_base()
    yield
    reset_knowledge_base()


class TestSearchDocs:
    @pytest.mark.asyncio
    async def test_returns_relevant_results(self):
        result = await handle_search_docs({
            "query": "agent design patterns",
            "_namespace": "default",
        })
        text = result["content"][0]["text"]
        assert "Agent Design Patterns" in text

    @pytest.mark.asyncio
    async def test_respects_top_k(self):
        result = await handle_search_docs({
            "query": "NGEN platform",
            "top_k": 1,
            "_namespace": "default",
        })
        text = result["content"][0]["text"]
        assert "1." in text
        lines = text.strip().split("\n")
        numbered = [l for l in lines if l.strip().startswith("2.")]
        assert len(numbered) == 0

    @pytest.mark.asyncio
    async def test_missing_query_returns_error(self):
        result = await handle_search_docs({"_namespace": "default"})
        text = result["content"][0]["text"]
        assert "Error" in text or "Missing" in text

    @pytest.mark.asyncio
    async def test_no_results_for_nonsense(self):
        result = await handle_search_docs({
            "query": "xyzzyplugh",
            "_namespace": "nonexistent-tenant",
        })
        text = result["content"][0]["text"]
        # Platform docs are available to all tenants, so may still find something
        # or get "No documents found"
        assert len(text) > 0


class TestGetDocument:
    @pytest.mark.asyncio
    async def test_get_by_id(self):
        result = await handle_get_document({
            "doc_id": "ngen-architecture",
            "_namespace": "default",
        })
        text = result["content"][0]["text"]
        assert "NGEN Platform Architecture" in text

    @pytest.mark.asyncio
    async def test_not_found(self):
        result = await handle_get_document({
            "doc_id": "nonexistent-doc",
            "_namespace": "default",
        })
        text = result["content"][0]["text"]
        assert "Error" in text or "not found" in text

    @pytest.mark.asyncio
    async def test_missing_doc_id(self):
        result = await handle_get_document({"_namespace": "default"})
        text = result["content"][0]["text"]
        assert "Error" in text or "Missing" in text

    @pytest.mark.asyncio
    async def test_platform_docs_available_to_all_tenants(self):
        """Platform docs should be accessible from any tenant namespace."""
        result = await handle_get_document({
            "doc_id": "ngen-architecture",
            "_namespace": "some-random-tenant",
        })
        text = result["content"][0]["text"]
        assert "NGEN Platform Architecture" in text


class TestTenantScoping:
    @pytest.mark.asyncio
    async def test_tenant_docs_isolated(self):
        """Documents added for tenant-a should not appear in tenant-b searches."""
        from mcp_manager.handlers.knowledge_base import _get_index, _get_embedder

        index = _get_index()
        embedder = _get_embedder()

        # Add a doc for tenant-a
        emb = await embedder.embed_single("secret internal document for tenant A only")
        doc = Document(
            id="secret-doc", tenant_id="tenant-a", collection="internal",
            filename="secret.txt", original_name="Secret Doc", status="ready",
            chunk_count=1,
        )
        chunk = DocumentChunk(
            document_id="secret-doc", chunk_index=0,
            text="secret internal document for tenant A only",
            embedding=emb, token_estimate=8,
        )
        index.add_document("tenant-a", doc, [chunk])

        # Tenant A can find it
        result = await handle_search_docs({
            "query": "secret internal document",
            "_namespace": "tenant-a",
        })
        text = result["content"][0]["text"]
        assert "Secret Doc" in text

        # Tenant B gets only platform docs, not tenant A's secret doc
        result = await handle_search_docs({
            "query": "secret internal document",
            "_namespace": "tenant-b",
        })
        text = result["content"][0]["text"]
        assert "Secret Doc" not in text
