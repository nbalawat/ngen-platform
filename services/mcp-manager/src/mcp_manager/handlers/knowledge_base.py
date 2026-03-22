"""Knowledge base handler — tenant-scoped vector search over uploaded documents.

Provides two tools:
- search_docs: Semantic search over documents using vector embeddings
- get_document: Retrieve a specific document by ID

Documents are scoped per tenant. The handler receives _namespace from the
transport layer to identify the tenant.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp_manager.documents.embeddings import EmbeddingProvider, LocalEmbeddingClient
from mcp_manager.documents.index import DocumentIndex
from mcp_manager.documents.models import Document, DocumentChunk

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state — initialized on app startup
# ---------------------------------------------------------------------------

_document_index: DocumentIndex | None = None
_embedding_client: EmbeddingProvider | None = None

# Platform seed tenant — used for pre-loaded documentation
_PLATFORM_TENANT = "platform"


def initialize_knowledge_base(
    document_index: DocumentIndex,
    embedding_client: EmbeddingProvider,
) -> None:
    """Initialize the knowledge base with a document index and embedding client.

    Called during app startup to wire dependencies.
    """
    global _document_index, _embedding_client
    _document_index = document_index
    _embedding_client = embedding_client
    logger.info("Knowledge base initialized with vector search")


def _get_index() -> DocumentIndex:
    if _document_index is None:
        raise RuntimeError("Knowledge base not initialized. Call initialize_knowledge_base() first.")
    return _document_index


def _get_embedder() -> EmbeddingProvider:
    if _embedding_client is None:
        raise RuntimeError("Embedding client not initialized.")
    return _embedding_client


def _mcp_text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _mcp_error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"Error: {message}"}]}


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def handle_search_docs(arguments: dict[str, Any]) -> dict[str, Any]:
    """Search documents by semantic similarity, scoped to tenant."""
    query = arguments.get("query", "").strip()
    if not query:
        return _mcp_error("Missing required parameter: query")

    # Tenant namespace injected by transport._invoke_builtin
    namespace = arguments.pop("_namespace", "default")
    collection = arguments.get("collection")
    top_k = min(int(arguments.get("top_k", 5)), 20)

    index = _get_index()
    embedder = _get_embedder()

    # Search in both the tenant's namespace and the platform docs
    try:
        query_embedding = await embedder.embed_single(query)
    except Exception as e:
        logger.error("Failed to generate query embedding: %s", e)
        return _mcp_error(f"Embedding generation failed: {e}")

    # Search tenant docs
    results = index.search(namespace, query_embedding, collection=collection, top_k=top_k)

    # Also search platform docs (available to all tenants)
    if namespace != _PLATFORM_TENANT:
        platform_results = index.search(
            _PLATFORM_TENANT, query_embedding, collection=collection, top_k=top_k,
        )
        results.extend(platform_results)
        # Re-sort by score and take top_k
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:top_k]

    if not results:
        return _mcp_text(f"No documents found matching: {query}")

    output = f"Found {len(results)} result(s) matching \"{query}\":\n\n"
    for i, r in enumerate(results, 1):
        snippet = r.chunk_text[:300] + "..." if len(r.chunk_text) > 300 else r.chunk_text
        output += f"{i}. **{r.document_title}** (id: {r.document_id}, collection: {r.collection}, relevance: {r.score:.2f})\n"
        output += f"   {snippet}\n\n"

    return _mcp_text(output)


async def handle_get_document(arguments: dict[str, Any]) -> dict[str, Any]:
    """Retrieve a document by ID, scoped to tenant."""
    doc_id = arguments.get("doc_id", "").strip()
    if not doc_id:
        return _mcp_error("Missing required parameter: doc_id")

    namespace = arguments.pop("_namespace", "default")
    index = _get_index()

    # Try tenant namespace first, then platform
    doc = index.get_document(namespace, doc_id)
    if doc is None and namespace != _PLATFORM_TENANT:
        doc = index.get_document(_PLATFORM_TENANT, doc_id)
        if doc is not None:
            namespace = _PLATFORM_TENANT

    if doc is None:
        return _mcp_error(f"Document not found: {doc_id}")

    # Get full text from chunks
    full_text = index.get_document_text(namespace, doc_id)
    if not full_text:
        full_text = "(No content available)"

    output = f"# {doc.original_name}\n\n"
    output += f"**Collection:** {doc.collection}\n"
    output += f"**Chunks:** {doc.chunk_count}\n"
    output += f"\n{full_text}"

    return _mcp_text(output)


# ---------------------------------------------------------------------------
# Seed data — pre-load platform documentation
# ---------------------------------------------------------------------------

_SEED_DOCS = [
    {
        "id": "ngen-architecture", "title": "NGEN Platform Architecture Overview",
        "collection": "architecture", "tags": ["architecture", "overview", "rapids"],
        "content": (
            "The NGEN platform is a multi-tenant, multi-agent orchestration system built on the RAPIDS methodology. "
            "It consists of several core services: Workflow Engine (agent orchestration and execution), "
            "Model Gateway (multi-provider LLM routing with cost tracking), Model Registry (model catalog and lifecycle), "
            "MCP Manager (tool catalog and invocation), Tenant Service (organization/team/project management), "
            "Governance Service (policy enforcement and budgets), and Metering Service (usage aggregation). "
            "The platform supports multiple agent frameworks including LangGraph, CrewAI, Claude Agent SDK, "
            "Google ADK, and Microsoft Agent Framework through a pluggable adapter architecture. "
            "All inter-service communication uses NATS for event-driven pub/sub messaging."
        ),
    },
    {
        "id": "ngen-getting-started", "title": "Getting Started with NGEN",
        "collection": "guides", "tags": ["getting-started", "tutorial"],
        "content": (
            "To get started with the NGEN platform: 1) Create an organization and team in the Tenant Service. "
            "2) Browse available models in the Model Catalog. 3) Explore the Tool Catalog for MCP tools. "
            "4) Create your first agent with a name, system prompt, and tools. "
            "5) Test your agent in the Agent Test Bench. "
            "6) Create a Workflow to orchestrate multiple agents. "
            "7) Choose a topology (Sequential, Parallel, Graph, or Hierarchical). "
            "8) Run and monitor execution in real-time via SSE streaming."
        ),
    },
    {
        "id": "ngen-agent-design", "title": "Agent Design Patterns",
        "collection": "guides", "tags": ["agents", "design-patterns"],
        "content": (
            "Effective agent design in NGEN follows these patterns: "
            "1) Single Responsibility: Each agent should focus on one task or domain. "
            "2) Tool-Augmented: Equip agents with specific tools. "
            "3) Clear System Prompts: Define the agent's role, constraints, and output format. "
            "4) Memory-Aware: Configure appropriate memory types. "
            "5) Escalation Rules: Define when to escalate. "
            "6) Cost Governance: Set budget limits per agent."
        ),
    },
    {
        "id": "ngen-workflow-patterns", "title": "Workflow Topology Patterns",
        "collection": "guides", "tags": ["workflows", "topology"],
        "content": (
            "NGEN supports four workflow topologies: "
            "Sequential: Agents execute one after another. "
            "Parallel: All agents run simultaneously. "
            "Graph (DAG): Directed acyclic graph with conditional edges. "
            "Hierarchical: First agent is supervisor that delegates tasks. "
            "All topologies support Human-in-the-Loop (HITL) approval gates."
        ),
    },
    {
        "id": "ngen-tool-integration", "title": "Tool Integration Guide",
        "collection": "guides", "tags": ["tools", "mcp"],
        "content": (
            "Tools in NGEN are provided via MCP (Model Context Protocol) servers. "
            "The platform offers built-in tools: Web Search, Knowledge Base, and more. "
            "Tenants can register custom MCP servers that expose their own tools. "
            "Custom servers must implement the MCP JSON-RPC 2.0 protocol."
        ),
    },
    {
        "id": "ngen-memory-system", "title": "Agent Memory System",
        "collection": "architecture", "tags": ["memory", "architecture"],
        "content": (
            "NGEN provides a 7-type memory system for agents: "
            "CONVERSATIONAL, KNOWLEDGE_BASE, WORKFLOW, TOOLBOX, ENTITY, SUMMARY, TOOL_LOG. "
            "Memory is scoped by tenant (org/team/project/agent/thread) for complete isolation."
        ),
    },
    {
        "id": "ngen-governance", "title": "Governance and Policy Framework",
        "collection": "architecture", "tags": ["governance", "policies"],
        "content": (
            "The NGEN governance framework enforces policies: "
            "Budget Policies, Rate Limits, Content Policies, Model Restrictions. "
            "Policies are evaluated in real-time during agent execution."
        ),
    },
    {
        "id": "ngen-api-reference", "title": "API Reference Summary",
        "collection": "reference", "tags": ["api", "reference"],
        "content": (
            "Key API endpoints: "
            "Workflow Engine (port 8003): POST /agents, POST /agents/{name}/invoke, POST /workflows/run. "
            "Model Gateway (port 8002): POST /v1/chat/completions, GET /v1/models. "
            "MCP Manager (port 8005): GET /api/v1/tools, POST /api/v1/invoke. "
            "All services use JSON request/response format with JWT authentication."
        ),
    },
]


async def seed_knowledge_base() -> None:
    """Pre-load platform documentation into the index with embeddings."""
    index = _get_index()
    embedder = _get_embedder()

    # Skip if already seeded
    if index.list_documents(_PLATFORM_TENANT):
        return

    logger.info("Seeding knowledge base with %d platform documents", len(_SEED_DOCS))

    for seed in _SEED_DOCS:
        # Generate embedding for the content
        try:
            embedding = await embedder.embed_single(seed["content"])
        except Exception:
            embedding = None

        doc = Document(
            id=seed["id"],
            tenant_id=_PLATFORM_TENANT,
            collection=seed["collection"],
            filename=f"{seed['id']}.md",
            original_name=seed["title"],
            status="ready",
            chunk_count=1,
            size_bytes=len(seed["content"]),
        )

        chunk = DocumentChunk(
            document_id=seed["id"],
            chunk_index=0,
            text=seed["content"],
            embedding=embedding,
            token_estimate=len(seed["content"].split()),
        )

        index.add_document(_PLATFORM_TENANT, doc, [chunk])

    logger.info("Knowledge base seeded with %d documents", len(_SEED_DOCS))


def reset_knowledge_base() -> None:
    """Clear all documents. Used by tests."""
    if _document_index is not None:
        _document_index.clear()
