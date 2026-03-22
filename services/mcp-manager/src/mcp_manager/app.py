"""FastAPI application for the MCP Manager service."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI

from mcp_manager.builtin_registry import BuiltinHandlerRegistry
from mcp_manager.documents.embeddings import GatewayEmbeddingClient, LocalEmbeddingClient
from mcp_manager.documents.index import DocumentIndex
from mcp_manager.documents.pipeline import DocumentProcessor
from mcp_manager.documents.routes import collection_router, document_router
from mcp_manager.documents.store import FileSystemDocumentStore
from mcp_manager.handlers import register_builtin_handlers
from mcp_manager.handlers.knowledge_base import initialize_knowledge_base
from mcp_manager.routes import invoke_router, server_router, tool_router
from mcp_manager.seed import seed_repository
from mcp_manager.transport import MCPTransport
from ngen_common.auth import add_auth
from ngen_common.auth_config import make_auth_config
from ngen_common.cors import add_cors
from ngen_common.error_handlers import add_error_handlers
from ngen_common.events import add_event_bus
from ngen_common.observability import add_observability

logger = logging.getLogger(__name__)


def create_app(
    mcp_transport: MCPTransport | None = None,
) -> FastAPI:
    application = FastAPI(
        title="NGEN MCP Manager",
        version="0.1.0",
    )

    # Document storage and indexing
    doc_store_path = os.environ.get("NGEN_DOCUMENT_STORE_PATH", "data/documents")
    document_store = FileSystemDocumentStore(base_dir=doc_store_path)
    document_index = DocumentIndex()

    # Embedding client — use gateway if URL configured, else local fallback
    gateway_url = os.environ.get("MODEL_GATEWAY_URL", "")
    if gateway_url:
        embedding_client = GatewayEmbeddingClient(gateway_url=gateway_url)
        logger.info("Using gateway embedding client: %s", gateway_url)
    else:
        embedding_client = LocalEmbeddingClient()
        logger.info("Using local embedding client (no MODEL_GATEWAY_URL configured)")

    # Initialize knowledge base with vector search
    initialize_knowledge_base(document_index, embedding_client)

    # Document processor pipeline
    document_processor = DocumentProcessor(
        store=document_store,
        index=document_index,
        embedding_client=embedding_client,
    )

    # Store on app state for route access
    application.state.document_store = document_store
    application.state.document_index = document_index
    application.state.document_processor = document_processor

    # Built-in handler registry for platform-provided tools
    builtin_registry = BuiltinHandlerRegistry()
    register_builtin_handlers(builtin_registry)
    logger.info(
        "Registered %d built-in tool handlers: %s",
        len(builtin_registry.registered_tools),
        builtin_registry.registered_tools,
    )

    # MCP transport with built-in handler support
    application.state.mcp_transport = mcp_transport or MCPTransport(
        builtin_registry=builtin_registry
    )

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    application.include_router(server_router)
    application.include_router(tool_router)
    application.include_router(invoke_router)
    application.include_router(document_router)
    application.include_router(collection_router)

    @application.on_event("startup")
    async def _seed_on_startup() -> None:
        from mcp_manager.routes import _get_repository
        repo = _get_repository()
        count = seed_repository(repo)
        if count:
            logger.info("Seeded %d MCP servers on startup", count)

        # Seed knowledge base with platform docs
        from mcp_manager.handlers.knowledge_base import seed_knowledge_base
        await seed_knowledge_base()

    add_error_handlers(application)
    add_cors(application)
    add_observability(application, service_name="mcp-manager")
    add_auth(application, make_auth_config())
    add_event_bus(application, service_name="mcp-manager")
    return application


app = create_app()
