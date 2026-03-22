"""Document management REST API — upload, list, delete."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel

from mcp_manager.documents.index import DocumentIndex
from mcp_manager.documents.models import Collection, Document, DocumentUploadResponse
from mcp_manager.documents.pipeline import DocumentProcessor

logger = logging.getLogger(__name__)

document_router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
collection_router = APIRouter(prefix="/api/v1/collections", tags=["collections"])

# ---------------------------------------------------------------------------
# In-memory collection store (future: database)
# ---------------------------------------------------------------------------

_collections: dict[str, dict[str, Collection]] = {}  # {tenant_id: {name: Collection}}


# ---------------------------------------------------------------------------
# Document endpoints
# ---------------------------------------------------------------------------


@document_router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    tenant_id: str = Form("default"),
    collection: str = Form("default"),
) -> DocumentUploadResponse:
    """Upload a document for processing and indexing."""
    processor: DocumentProcessor = request.app.state.document_processor

    content = await file.read()
    filename = file.filename or "unnamed"

    doc = await processor.process(
        tenant_id=tenant_id,
        collection=collection,
        filename=filename,
        content=content,
    )

    if doc.status == "error":
        raise HTTPException(
            status_code=400,
            detail=doc.error_message or "Document processing failed",
        )

    # Auto-create collection if it doesn't exist
    _ensure_collection(tenant_id, collection)

    return DocumentUploadResponse(
        document_id=doc.id,
        filename=doc.original_name,
        chunk_count=doc.chunk_count,
        status=doc.status,
    )


@document_router.get("")
async def list_documents(
    request: Request,
    tenant_id: str = "default",
    collection: str | None = None,
) -> list[dict[str, Any]]:
    """List documents for a tenant, optionally filtered by collection."""
    index: DocumentIndex = request.app.state.document_index
    docs = index.list_documents(tenant_id, collection=collection)
    return [_doc_to_dict(d) for d in docs]


@document_router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    request: Request,
    tenant_id: str = "default",
) -> dict[str, Any]:
    """Get document metadata."""
    index: DocumentIndex = request.app.state.document_index
    doc = index.get_document(tenant_id, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    return _doc_to_dict(doc)


@document_router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    request: Request,
    tenant_id: str = "default",
) -> None:
    """Delete a document and its chunks."""
    index: DocumentIndex = request.app.state.document_index
    from mcp_manager.documents.store import DocumentStore
    store: DocumentStore = request.app.state.document_store

    doc = index.get_document(tenant_id, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")

    # Delete from index
    index.delete_document(tenant_id, doc_id)

    # Delete from file store
    try:
        store.delete(tenant_id, doc.collection, doc.filename)
    except FileNotFoundError:
        pass  # File may have been cleaned up already


# ---------------------------------------------------------------------------
# Collection endpoints
# ---------------------------------------------------------------------------


class CollectionCreate(BaseModel):
    tenant_id: str = "default"
    name: str
    description: str = ""


@collection_router.post("", response_model=dict)
async def create_collection(body: CollectionCreate) -> dict[str, Any]:
    """Create a named document collection."""
    col = _ensure_collection(body.tenant_id, body.name, body.description)
    return _col_to_dict(col)


@collection_router.get("")
async def list_collections(
    request: Request,
    tenant_id: str = "default",
) -> list[dict[str, Any]]:
    """List collections for a tenant."""
    index: DocumentIndex = request.app.state.document_index
    tenant_cols = _collections.get(tenant_id, {})

    # Also include collections from indexed documents
    indexed_collections = index.list_collections(tenant_id)
    for name in indexed_collections:
        if name not in tenant_cols:
            _ensure_collection(tenant_id, name)

    result = []
    for col in _collections.get(tenant_id, {}).values():
        col_dict = _col_to_dict(col)
        col_dict["document_count"] = index.collection_doc_count(tenant_id, col.name)
        result.append(col_dict)

    return result


@collection_router.delete("/{collection_name}", status_code=204)
async def delete_collection(
    collection_name: str,
    request: Request,
    tenant_id: str = "default",
) -> None:
    """Delete a collection and all its documents."""
    index: DocumentIndex = request.app.state.document_index
    store = request.app.state.document_store

    count = index.delete_collection(tenant_id, collection_name)

    # Delete files
    try:
        store.delete_collection(tenant_id, collection_name)
    except Exception:
        pass

    # Remove collection metadata
    tenant_cols = _collections.get(tenant_id, {})
    tenant_cols.pop(collection_name, None)

    if count == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Collection not found: {collection_name}",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_collection(
    tenant_id: str, name: str, description: str = "",
) -> Collection:
    tenant_cols = _collections.setdefault(tenant_id, {})
    if name not in tenant_cols:
        tenant_cols[name] = Collection(
            name=name, tenant_id=tenant_id, description=description,
        )
    return tenant_cols[name]


def _doc_to_dict(doc: Document) -> dict[str, Any]:
    return {
        "id": doc.id,
        "tenant_id": doc.tenant_id,
        "collection": doc.collection,
        "filename": doc.filename,
        "original_name": doc.original_name,
        "content_type": doc.content_type,
        "size_bytes": doc.size_bytes,
        "chunk_count": doc.chunk_count,
        "status": doc.status,
        "created_at": doc.created_at,
    }


def _col_to_dict(col: Collection) -> dict[str, Any]:
    return {
        "id": col.id,
        "name": col.name,
        "tenant_id": col.tenant_id,
        "description": col.description,
        "document_count": col.document_count,
        "created_at": col.created_at,
    }
