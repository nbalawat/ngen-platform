"""Built-in tool handlers for platform-provided MCP tools."""

from __future__ import annotations

from mcp_manager.builtin_registry import BuiltinHandlerRegistry
from mcp_manager.handlers.knowledge_base import (
    handle_get_document,
    handle_search_docs,
)
from mcp_manager.handlers.web_search import handle_fetch_page, handle_search
from mcp_manager.handlers.document_intelligence import (
    handle_extract,
    handle_parse,
    handle_split,
)


def register_builtin_handlers(registry: BuiltinHandlerRegistry) -> None:
    """Register all built-in tool handlers."""
    # Web Search
    registry.register("web-search", "search", handle_search)
    registry.register("web-search", "fetch_page", handle_fetch_page)

    # Knowledge Base (seed happens on app startup via seed_knowledge_base())
    registry.register("knowledge-base", "search_docs", handle_search_docs)
    registry.register("knowledge-base", "get_document", handle_get_document)

    # Document Intelligence (Landing.ai ADE)
    registry.register("document-intelligence", "parse_document", handle_parse)
    registry.register("document-intelligence", "split_document", handle_split)
    registry.register("document-intelligence", "extract_data", handle_extract)
