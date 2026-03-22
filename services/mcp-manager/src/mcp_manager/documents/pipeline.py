"""Document processing pipeline — upload → parse → chunk → embed → index."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from mcp_manager.documents.chunker import chunk_text
from mcp_manager.documents.embeddings import EmbeddingProvider
from mcp_manager.documents.index import DocumentIndex
from mcp_manager.documents.models import Document, DocumentChunk
from mcp_manager.documents.parser import UnsupportedFormatError, parse_document
from mcp_manager.documents.store import DocumentStore

logger = logging.getLogger(__name__)

# 50 MB default file size limit
MAX_FILE_SIZE = int(os.environ.get("NGEN_MAX_DOCUMENT_SIZE", 50 * 1024 * 1024))

ALLOWED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".docx"}


class DocumentProcessor:
    """Orchestrates the full document ingestion pipeline."""

    def __init__(
        self,
        store: DocumentStore,
        index: DocumentIndex,
        embedding_client: EmbeddingProvider,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
    ) -> None:
        self._store = store
        self._index = index
        self._embedder = embedding_client
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    async def process(
        self,
        tenant_id: str,
        collection: str,
        filename: str,
        content: bytes,
    ) -> Document:
        """Process a document through the full pipeline.

        Returns Document metadata with status = "ready" on success,
        or status = "error" with error_message on failure.
        """
        doc_id = uuid.uuid4().hex[:12]
        ext = os.path.splitext(filename)[1].lower()

        # Create document record
        doc = Document(
            id=doc_id,
            tenant_id=tenant_id,
            collection=collection,
            filename=f"{doc_id}{ext}",
            original_name=filename,
            content_type=self._content_type(ext),
            size_bytes=len(content),
            status="processing",
        )

        try:
            # Validate
            if len(content) > MAX_FILE_SIZE:
                raise ValueError(
                    f"File too large: {len(content)} bytes (max {MAX_FILE_SIZE})"
                )
            if ext not in ALLOWED_EXTENSIONS:
                raise UnsupportedFormatError(ext)

            # 1. Save raw file
            self._store.save(tenant_id, collection, doc.filename, content)

            # 2. Extract text
            text = parse_document(filename, content)
            if not text.strip():
                raise ValueError("No text content could be extracted from the file")

            # 3. Chunk
            text_chunks = chunk_text(
                text,
                chunk_size=self._chunk_size,
                overlap=self._chunk_overlap,
            )

            if not text_chunks:
                raise ValueError("Text chunking produced no chunks")

            # 4. Generate embeddings (batched)
            chunk_texts = [c.text for c in text_chunks]
            embeddings = await self._embedder.embed(chunk_texts)

            # 5. Create DocumentChunk objects
            doc_chunks = []
            for tc, emb in zip(text_chunks, embeddings):
                doc_chunks.append(DocumentChunk(
                    document_id=doc_id,
                    chunk_index=tc.chunk_index,
                    text=tc.text,
                    embedding=emb,
                    token_estimate=tc.token_estimate,
                    start_char=tc.start_char,
                    end_char=tc.end_char,
                ))

            # 6. Index
            doc.chunk_count = len(doc_chunks)
            doc.status = "ready"
            self._index.add_document(tenant_id, doc, doc_chunks)

            logger.info(
                "Processed document '%s' for tenant '%s': %d chunks",
                filename, tenant_id, len(doc_chunks),
            )
            return doc

        except Exception as e:
            doc.status = "error"
            doc.error_message = str(e)
            logger.error(
                "Failed to process document '%s': %s", filename, e,
            )
            return doc

    @staticmethod
    def _content_type(ext: str) -> str:
        return {
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".markdown": "text/markdown",
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }.get(ext, "application/octet-stream")
