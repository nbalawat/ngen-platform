"""Tests for document index — tenant isolation, vector search."""

from __future__ import annotations

import pytest

from mcp_manager.documents.embeddings import LocalEmbeddingClient
from mcp_manager.documents.index import DocumentIndex
from mcp_manager.documents.models import Document, DocumentChunk


@pytest.fixture()
def index():
    idx = DocumentIndex()
    yield idx
    idx.clear()


@pytest.fixture()
def embedding_client():
    return LocalEmbeddingClient(dimension=64)


def _make_doc(tenant_id, collection, doc_id, name):
    return Document(
        id=doc_id, tenant_id=tenant_id, collection=collection,
        filename=name, original_name=name, status="ready",
    )


def _make_chunks(doc_id, texts, embeddings):
    return [
        DocumentChunk(
            document_id=doc_id, chunk_index=i,
            text=t, embedding=e, token_estimate=len(t.split()),
        )
        for i, (t, e) in enumerate(zip(texts, embeddings))
    ]


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_tenant_a_cannot_see_tenant_b(self, index, embedding_client):
        """Documents indexed under tenant A are invisible to tenant B."""
        emb = await embedding_client.embed(["secret data from tenant A"])

        doc = _make_doc("tenant-a", "docs", "doc-1", "secret.txt")
        chunks = _make_chunks("doc-1", ["secret data from tenant A"], emb)
        index.add_document("tenant-a", doc, chunks)

        # Tenant A can find it
        query_emb = await embedding_client.embed_single("secret data")
        results_a = index.search("tenant-a", query_emb)
        assert len(results_a) > 0

        # Tenant B cannot
        results_b = index.search("tenant-b", query_emb)
        assert len(results_b) == 0

    @pytest.mark.asyncio
    async def test_get_document_scoped(self, index, embedding_client):
        doc = _make_doc("tenant-a", "docs", "doc-1", "test.txt")
        index.add_document("tenant-a", doc, [])

        assert index.get_document("tenant-a", "doc-1") is not None
        assert index.get_document("tenant-b", "doc-1") is None


class TestVectorSearch:
    @pytest.mark.asyncio
    async def test_cosine_ranking(self, index, embedding_client):
        """More relevant chunks should rank higher."""
        texts = [
            "machine learning and deep neural networks",
            "cooking pasta with tomato sauce",
            "artificial intelligence and machine learning",
        ]
        embeddings = await embedding_client.embed(texts)

        for i, (text, emb) in enumerate(zip(texts, embeddings)):
            doc = _make_doc("t1", "docs", f"doc-{i}", f"doc{i}.txt")
            chunks = _make_chunks(f"doc-{i}", [text], [emb])
            index.add_document("t1", doc, chunks)

        # Search for ML — should rank ML docs above cooking
        query = await embedding_client.embed_single("machine learning neural networks")
        results = index.search("t1", query, top_k=3)

        assert len(results) == 3
        # The top results should be about ML, not cooking
        assert "cooking" not in results[0].chunk_text.lower()

    @pytest.mark.asyncio
    async def test_collection_filter(self, index, embedding_client):
        emb = await embedding_client.embed(["some text"])

        doc_a = _make_doc("t1", "collection-a", "doc-a", "a.txt")
        doc_b = _make_doc("t1", "collection-b", "doc-b", "b.txt")
        index.add_document("t1", doc_a, _make_chunks("doc-a", ["some text"], emb))
        index.add_document("t1", doc_b, _make_chunks("doc-b", ["some text"], emb))

        query = await embedding_client.embed_single("some text")
        results = index.search("t1", query, collection="collection-a")
        assert all(r.collection == "collection-a" for r in results)

    @pytest.mark.asyncio
    async def test_top_k_limit(self, index, embedding_client):
        for i in range(10):
            text = f"document number {i} about topic"
            emb = await embedding_client.embed([text])
            doc = _make_doc("t1", "docs", f"doc-{i}", f"doc{i}.txt")
            index.add_document("t1", doc, _make_chunks(f"doc-{i}", [text], emb))

        query = await embedding_client.embed_single("topic")
        results = index.search("t1", query, top_k=3)
        assert len(results) == 3


class TestDocumentManagement:
    def test_list_documents(self, index):
        doc1 = _make_doc("t1", "docs", "d1", "a.txt")
        doc2 = _make_doc("t1", "other", "d2", "b.txt")
        index.add_document("t1", doc1, [])
        index.add_document("t1", doc2, [])

        all_docs = index.list_documents("t1")
        assert len(all_docs) == 2

        filtered = index.list_documents("t1", collection="docs")
        assert len(filtered) == 1
        assert filtered[0].id == "d1"

    def test_delete_document(self, index):
        doc = _make_doc("t1", "docs", "d1", "test.txt")
        index.add_document("t1", doc, [])

        assert index.delete_document("t1", "d1") is True
        assert index.get_document("t1", "d1") is None
        assert index.delete_document("t1", "d1") is False

    def test_list_collections(self, index):
        index.add_document("t1", _make_doc("t1", "alpha", "d1", "a.txt"), [])
        index.add_document("t1", _make_doc("t1", "beta", "d2", "b.txt"), [])

        collections = index.list_collections("t1")
        assert collections == ["alpha", "beta"]

    def test_delete_collection(self, index):
        index.add_document("t1", _make_doc("t1", "docs", "d1", "a.txt"), [])
        index.add_document("t1", _make_doc("t1", "docs", "d2", "b.txt"), [])
        index.add_document("t1", _make_doc("t1", "other", "d3", "c.txt"), [])

        count = index.delete_collection("t1", "docs")
        assert count == 2
        assert len(index.list_documents("t1")) == 1
