"""Document index — vector storage and search with tenant isolation.

Stores document chunks with embeddings in memory. Supports cosine
similarity search scoped per tenant and collection.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from mcp_manager.documents.models import Document, DocumentChunk, SearchResult

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class DocumentIndex:
    """In-memory vector document index with tenant isolation.

    All operations are scoped by tenant_id to prevent cross-tenant data leakage.
    """

    def __init__(self) -> None:
        # {tenant_id: {doc_id: Document}}
        self._documents: dict[str, dict[str, Document]] = {}
        # {tenant_id: {doc_id: [DocumentChunk]}}
        self._chunks: dict[str, dict[str, list[DocumentChunk]]] = {}
        # {tenant_id: [collection_name]}
        self._collections: dict[str, set[str]] = {}

    def add_document(
        self,
        tenant_id: str,
        doc: Document,
        chunks: list[DocumentChunk],
    ) -> None:
        """Add a document with its chunks to the index."""
        self._documents.setdefault(tenant_id, {})[doc.id] = doc
        self._chunks.setdefault(tenant_id, {})[doc.id] = chunks
        self._collections.setdefault(tenant_id, set()).add(doc.collection)
        logger.info(
            "Indexed document '%s' for tenant '%s': %d chunks",
            doc.filename, tenant_id, len(chunks),
        )

    def search(
        self,
        tenant_id: str,
        query_embedding: list[float],
        collection: str | None = None,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Vector similarity search scoped to a tenant."""
        tenant_docs = self._documents.get(tenant_id, {})
        tenant_chunks = self._chunks.get(tenant_id, {})

        scored: list[tuple[SearchResult, float]] = []

        for doc_id, doc in tenant_docs.items():
            # Filter by collection if specified
            if collection and doc.collection != collection:
                continue

            # Only search documents that are ready
            if doc.status != "ready":
                continue

            for chunk in tenant_chunks.get(doc_id, []):
                if chunk.embedding is None:
                    continue

                score = _cosine_similarity(query_embedding, chunk.embedding)
                scored.append((
                    SearchResult(
                        chunk_text=chunk.text,
                        document_id=doc_id,
                        document_title=doc.original_name,
                        collection=doc.collection,
                        score=score,
                        chunk_index=chunk.chunk_index,
                    ),
                    score,
                ))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return [sr for sr, _ in scored[:top_k]]

    def get_document(self, tenant_id: str, doc_id: str) -> Document | None:
        """Get document metadata by ID, scoped to tenant."""
        return self._documents.get(tenant_id, {}).get(doc_id)

    def get_document_chunks(
        self, tenant_id: str, doc_id: str,
    ) -> list[DocumentChunk]:
        """Get all chunks for a document, scoped to tenant."""
        return self._chunks.get(tenant_id, {}).get(doc_id, [])

    def get_document_text(self, tenant_id: str, doc_id: str) -> str | None:
        """Get full document text by concatenating chunks."""
        chunks = self.get_document_chunks(tenant_id, doc_id)
        if not chunks:
            return None
        sorted_chunks = sorted(chunks, key=lambda c: c.chunk_index)
        return "\n\n".join(c.text for c in sorted_chunks)

    def list_documents(
        self, tenant_id: str, collection: str | None = None,
    ) -> list[Document]:
        """List documents for a tenant, optionally filtered by collection."""
        docs = list(self._documents.get(tenant_id, {}).values())
        if collection:
            docs = [d for d in docs if d.collection == collection]
        return sorted(docs, key=lambda d: d.created_at, reverse=True)

    def delete_document(self, tenant_id: str, doc_id: str) -> bool:
        """Delete a document and its chunks. Returns True if it existed."""
        tenant_docs = self._documents.get(tenant_id, {})
        if doc_id not in tenant_docs:
            return False
        del tenant_docs[doc_id]
        self._chunks.get(tenant_id, {}).pop(doc_id, None)
        return True

    def list_collections(self, tenant_id: str) -> list[str]:
        """List collection names for a tenant."""
        return sorted(self._collections.get(tenant_id, set()))

    def collection_doc_count(self, tenant_id: str, collection: str) -> int:
        """Count documents in a collection."""
        return len([
            d for d in self._documents.get(tenant_id, {}).values()
            if d.collection == collection
        ])

    def delete_collection(self, tenant_id: str, collection: str) -> int:
        """Delete all documents in a collection. Returns count deleted."""
        tenant_docs = self._documents.get(tenant_id, {})
        to_delete = [
            doc_id for doc_id, doc in tenant_docs.items()
            if doc.collection == collection
        ]
        for doc_id in to_delete:
            self.delete_document(tenant_id, doc_id)
        self._collections.get(tenant_id, set()).discard(collection)
        return len(to_delete)

    def clear(self) -> None:
        """Clear all data. Used by tests."""
        self._documents.clear()
        self._chunks.clear()
        self._collections.clear()
