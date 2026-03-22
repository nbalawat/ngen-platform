"""Seed data for the MCP Manager — realistic platform tools.

Registers a curated set of MCP servers and tools on startup so tenants
see a useful tool catalog from day one.
"""

from __future__ import annotations

import logging

from mcp_manager.models import ServerCreate, ToolDefinition, ToolParameter, TransportType
from mcp_manager.repository import MCPRepository

logger = logging.getLogger(__name__)

_SEED_SERVERS: list[ServerCreate] = [
    ServerCreate(
        name="web-search",
        description="Web search and retrieval — search the internet for real-time information",
        endpoint="builtin://web-search",
        transport=TransportType.BUILTIN,
        tools=[
            ToolDefinition(
                name="search",
                description="Search the web for information on any topic. Returns relevant results with titles, snippets, and URLs.",
                parameters=[
                    ToolParameter(name="query", type="string", description="Search query", required=True),
                    ToolParameter(name="max_results", type="integer", description="Maximum number of results (1-10)", required=False),
                ],
                tags=["search", "web", "research"],
            ),
            ToolDefinition(
                name="fetch_page",
                description="Fetch and extract the main content from a web page URL.",
                parameters=[
                    ToolParameter(name="url", type="string", description="URL to fetch", required=True),
                ],
                tags=["web", "fetch", "scrape"],
            ),
        ],
    ),
    ServerCreate(
        name="knowledge-base",
        description="Vector-based knowledge retrieval — search internal documents and knowledge bases",
        endpoint="builtin://knowledge-base",
        transport=TransportType.BUILTIN,
        tools=[
            ToolDefinition(
                name="search_docs",
                description="Semantic search across your organization's documents, wikis, and knowledge base articles.",
                parameters=[
                    ToolParameter(name="query", type="string", description="Natural language search query", required=True),
                    ToolParameter(name="collection", type="string", description="Document collection to search (default: all)", required=False),
                    ToolParameter(name="top_k", type="integer", description="Number of results to return", required=False),
                ],
                tags=["knowledge", "search", "documents", "rag"],
            ),
            ToolDefinition(
                name="get_document",
                description="Retrieve a specific document by ID from the knowledge base.",
                parameters=[
                    ToolParameter(name="doc_id", type="string", description="Document identifier", required=True),
                ],
                tags=["knowledge", "documents"],
            ),
        ],
    ),
    ServerCreate(
        name="database-query",
        description="SQL database access — query structured data from connected databases",
        endpoint="http://mcp-database:8080/mcp",
        tools=[
            ToolDefinition(
                name="sql_query",
                description="Execute a read-only SQL query against the connected database. Returns tabular results.",
                parameters=[
                    ToolParameter(name="query", type="string", description="SQL SELECT query to execute", required=True),
                    ToolParameter(name="database", type="string", description="Target database name", required=False),
                    ToolParameter(name="limit", type="integer", description="Max rows to return (default: 100)", required=False),
                ],
                tags=["database", "sql", "analytics"],
            ),
            ToolDefinition(
                name="list_tables",
                description="List available tables and their schemas in the connected database.",
                parameters=[
                    ToolParameter(name="database", type="string", description="Target database name", required=False),
                ],
                tags=["database", "schema"],
            ),
        ],
    ),
    ServerCreate(
        name="code-interpreter",
        description="Sandboxed code execution — run Python code for calculations, data analysis, and chart generation",
        endpoint="http://mcp-code-interpreter:8080/mcp",
        tools=[
            ToolDefinition(
                name="execute_python",
                description="Execute Python code in a sandboxed environment. Supports pandas, numpy, matplotlib. Returns stdout, stderr, and generated files.",
                parameters=[
                    ToolParameter(name="code", type="string", description="Python code to execute", required=True),
                    ToolParameter(name="timeout_seconds", type="integer", description="Max execution time (default: 30)", required=False),
                ],
                tags=["code", "python", "analysis", "computation"],
            ),
        ],
    ),
    ServerCreate(
        name="email-service",
        description="Email integration — send emails and search mailboxes",
        endpoint="http://mcp-email:8080/mcp",
        tools=[
            ToolDefinition(
                name="send_email",
                description="Compose and send an email to one or more recipients.",
                parameters=[
                    ToolParameter(name="to", type="string", description="Recipient email address(es), comma-separated", required=True),
                    ToolParameter(name="subject", type="string", description="Email subject line", required=True),
                    ToolParameter(name="body", type="string", description="Email body (supports markdown)", required=True),
                    ToolParameter(name="cc", type="string", description="CC recipients", required=False),
                ],
                tags=["email", "communication"],
            ),
            ToolDefinition(
                name="search_inbox",
                description="Search emails in the connected mailbox by keyword, sender, or date range.",
                parameters=[
                    ToolParameter(name="query", type="string", description="Search query", required=True),
                    ToolParameter(name="from_address", type="string", description="Filter by sender", required=False),
                    ToolParameter(name="days_back", type="integer", description="Search last N days (default: 30)", required=False),
                ],
                tags=["email", "search"],
            ),
        ],
    ),
    ServerCreate(
        name="slack-integration",
        description="Slack workspace integration — post messages and search channels",
        endpoint="http://mcp-slack:8080/mcp",
        tools=[
            ToolDefinition(
                name="post_message",
                description="Post a message to a Slack channel.",
                parameters=[
                    ToolParameter(name="channel", type="string", description="Channel name or ID", required=True),
                    ToolParameter(name="message", type="string", description="Message text (supports Slack markdown)", required=True),
                ],
                tags=["slack", "communication", "messaging"],
            ),
            ToolDefinition(
                name="search_messages",
                description="Search for messages across Slack channels.",
                parameters=[
                    ToolParameter(name="query", type="string", description="Search query", required=True),
                    ToolParameter(name="channel", type="string", description="Limit to specific channel", required=False),
                ],
                tags=["slack", "search"],
            ),
        ],
    ),
    ServerCreate(
        name="file-manager",
        description="File system operations — read, write, and manage files in workspace storage",
        endpoint="http://mcp-files:8080/mcp",
        tools=[
            ToolDefinition(
                name="read_file",
                description="Read the contents of a file from workspace storage.",
                parameters=[
                    ToolParameter(name="path", type="string", description="File path relative to workspace root", required=True),
                ],
                tags=["filesystem", "read"],
            ),
            ToolDefinition(
                name="write_file",
                description="Write content to a file in workspace storage.",
                parameters=[
                    ToolParameter(name="path", type="string", description="File path relative to workspace root", required=True),
                    ToolParameter(name="content", type="string", description="File content to write", required=True),
                ],
                tags=["filesystem", "write"],
            ),
            ToolDefinition(
                name="list_files",
                description="List files and directories at a given path in workspace storage.",
                parameters=[
                    ToolParameter(name="path", type="string", description="Directory path (default: root)", required=False),
                    ToolParameter(name="pattern", type="string", description="Glob pattern to filter (e.g. '*.py')", required=False),
                ],
                tags=["filesystem", "list"],
            ),
        ],
    ),
    # ── Document Intelligence (Landing.ai ADE) ──────────────────────────
    ServerCreate(
        name="document-intelligence",
        description="AI-powered document parsing, splitting, and structured data extraction (Landing.ai ADE)",
        endpoint="builtin://document-intelligence",
        transport=TransportType.BUILTIN,
        tools=[
            ToolDefinition(
                name="parse_document",
                description="Parse a document (PDF, image, etc.) into structured markdown with chunk metadata. Provides rich document understanding including tables, figures, and text layout.",
                parameters=[
                    ToolParameter(name="url", type="string", description="URL of the document to parse", required=False),
                    ToolParameter(name="doc_id", type="string", description="ID of a document in the knowledge base", required=False),
                    ToolParameter(name="model", type="string", description="Parse model to use (default: dpt-2-latest)", required=False),
                ],
                tags=["document", "parse", "ocr", "pdf", "ai"],
            ),
            ToolDefinition(
                name="split_document",
                description="Split a multi-document file into classified sub-documents. Useful for separating combined PDFs (e.g., invoices + receipts) into individual documents.",
                parameters=[
                    ToolParameter(name="markdown", type="string", description="Parsed markdown content (from parse_document)", required=True),
                    ToolParameter(name="split_rules", type="string", description='JSON array of classification rules, e.g. [{"name":"Invoice","description":"Payment request document"}]', required=True),
                    ToolParameter(name="model", type="string", description="Split model to use (default: split-latest)", required=False),
                ],
                tags=["document", "split", "classify"],
            ),
            ToolDefinition(
                name="extract_data",
                description="Extract structured data from a document using a JSON schema. Define the fields you want to extract and get back structured key-value data.",
                parameters=[
                    ToolParameter(name="markdown", type="string", description="Parsed markdown content (from parse_document)", required=True),
                    ToolParameter(name="schema", type="string", description='JSON schema defining fields to extract, e.g. {"type":"object","properties":{"name":{"type":"string","description":"Person name"}}}', required=True),
                    ToolParameter(name="model", type="string", description="Extract model to use (default: extract-latest)", required=False),
                ],
                tags=["document", "extract", "structured-data", "schema"],
            ),
        ],
    ),
]


def seed_repository(repo: MCPRepository) -> int:
    """Seed the repository with platform tools if empty. Returns count of servers added."""
    existing = repo.list_servers()
    if existing:
        return 0

    count = 0
    for server_data in _SEED_SERVERS:
        try:
            repo.create_server(server_data)
            count += 1
            logger.info(
                "Seeded MCP server '%s' with %d tools",
                server_data.name,
                len(server_data.tools),
            )
        except Exception as e:
            logger.warning("Failed to seed server '%s': %s", server_data.name, e)

    logger.info("Seeded %d MCP servers with tools", count)
    return count
