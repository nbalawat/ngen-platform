"""Pydantic models for document management."""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> float:
    return time.time()


class DocumentChunk(BaseModel):
    """A chunk of a document with optional embedding."""

    id: str = Field(default_factory=_new_id)
    document_id: str
    chunk_index: int
    text: str
    embedding: list[float] | None = None
    token_estimate: int = 0
    start_char: int = 0
    end_char: int = 0


class Document(BaseModel):
    """Metadata for an uploaded document."""

    id: str = Field(default_factory=_new_id)
    tenant_id: str
    collection: str
    filename: str
    original_name: str
    content_type: str = "text/plain"
    size_bytes: int = 0
    chunk_count: int = 0
    status: str = "processing"  # processing | ready | error
    error_message: str | None = None
    created_at: float = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Collection(BaseModel):
    """A named collection of documents within a tenant."""

    id: str = Field(default_factory=_new_id)
    name: str
    tenant_id: str
    description: str = ""
    document_count: int = 0
    created_at: float = Field(default_factory=_now)


class DocumentUploadResponse(BaseModel):
    """Response from document upload."""

    document_id: str
    filename: str
    chunk_count: int
    status: str


class SearchResult(BaseModel):
    """A search result from vector similarity search."""

    chunk_text: str
    document_id: str
    document_title: str
    collection: str
    score: float
    chunk_index: int
