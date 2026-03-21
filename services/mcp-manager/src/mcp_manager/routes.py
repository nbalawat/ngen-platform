"""REST API routes for the MCP Manager service.

Provides:
- Server CRUD: register, list, get, update, delete MCP servers
- Tool catalog: list tools, search tools, get tool details
- Tool invocation: call a tool on a registered server (stub for now)
"""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException, Query, Request

from mcp_manager.models import (
    Server,
    ServerCreate,
    ServerUpdate,
    ToolCallRequest,
    ToolCallResponse,
    ToolEntry,
)
from mcp_manager.repository import MCPRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singletons — reset in tests via conftest
# ---------------------------------------------------------------------------

_repository: MCPRepository | None = None


def _get_repository() -> MCPRepository:
    global _repository
    if _repository is None:
        _repository = MCPRepository()
    return _repository


def _publish_lifecycle_event(
    request: Request, subject: str, data: dict,
) -> None:
    """Fire-and-forget lifecycle event publishing."""
    bus = getattr(request.app.state, "event_bus", None)
    if bus is None:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(bus.publish(subject, data, source="mcp-manager"))
    except RuntimeError:
        pass


# ---------------------------------------------------------------------------
# Server routes
# ---------------------------------------------------------------------------

server_router = APIRouter(prefix="/api/v1/servers", tags=["servers"])


@server_router.post("", status_code=201, response_model=Server)
async def register_server(body: ServerCreate, request: Request) -> Server:
    repo = _get_repository()
    existing = repo.get_server_by_name(body.name, body.namespace)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Server '{body.name}' already registered in namespace '{body.namespace}'",
        )
    server = repo.create_server(body)

    from ngen_common.events import Subjects
    _publish_lifecycle_event(request, Subjects.LIFECYCLE_SERVER_REGISTERED, {
        "server_id": server.id,
        "name": server.name,
        "namespace": server.namespace,
        "transport": server.transport,
        "endpoint": server.endpoint,
        "tool_count": len(server.tools),
    })
    return server


@server_router.get("", response_model=list[Server])
async def list_servers(
    namespace: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> list[Server]:
    return _get_repository().list_servers(namespace=namespace, status=status)


@server_router.get("/{server_id}", response_model=Server)
async def get_server(server_id: str) -> Server:
    server = _get_repository().get_server(server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    return server


@server_router.get("/by-name/{name}", response_model=Server)
async def get_server_by_name(
    name: str,
    namespace: str = Query(default="default"),
) -> Server:
    server = _get_repository().get_server_by_name(name, namespace)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    return server


@server_router.patch("/{server_id}", response_model=Server)
async def update_server(server_id: str, body: ServerUpdate) -> Server:
    server = _get_repository().update_server(server_id, body)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    return server


@server_router.delete("/{server_id}", status_code=204)
async def delete_server(server_id: str, request: Request) -> None:
    repo = _get_repository()
    server = repo.get_server(server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="Server not found")
    if not repo.delete_server(server_id):
        raise HTTPException(status_code=404, detail="Server not found")

    from ngen_common.events import Subjects
    _publish_lifecycle_event(request, Subjects.LIFECYCLE_SERVER_DELETED, {
        "server_id": server.id,
        "name": server.name,
        "namespace": server.namespace,
    })


# ---------------------------------------------------------------------------
# Tool catalog routes
# ---------------------------------------------------------------------------

tool_router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


@tool_router.get("", response_model=list[ToolEntry])
async def list_tools(
    server: str | None = Query(default=None, alias="server_name"),
    tag: str | None = Query(default=None),
) -> list[ToolEntry]:
    return _get_repository().list_tools(server_name=server, tag=tag)


@tool_router.get("/search", response_model=list[ToolEntry])
async def search_tools(
    q: str = Query(..., min_length=1),
) -> list[ToolEntry]:
    return _get_repository().search_tools(q)


@tool_router.get("/{tool_id}", response_model=ToolEntry)
async def get_tool(tool_id: str) -> ToolEntry:
    tool = _get_repository().get_tool(tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


# ---------------------------------------------------------------------------
# Tool invocation
# ---------------------------------------------------------------------------

invoke_router = APIRouter(prefix="/api/v1", tags=["invocation"])


@invoke_router.post("/invoke", response_model=ToolCallResponse)
async def invoke_tool(body: ToolCallRequest, request: Request) -> ToolCallResponse:
    """Invoke a tool on a registered MCP server.

    Dispatches the call to the actual MCP server using the appropriate
    transport (streamable-http, sse). Validates server and tool exist,
    then proxies the JSON-RPC tools/call request.
    """
    from mcp_manager.transport import MCPTransport, MCPTransportError

    repo = _get_repository()
    server = repo.get_server_by_name(body.server_name, body.namespace)
    if server is None:
        raise HTTPException(
            status_code=404,
            detail=f"Server '{body.server_name}' not found in namespace '{body.namespace}'",
        )

    tool = repo.find_tool(body.server_name, body.tool_name)
    if tool is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{body.tool_name}' not found on server '{body.server_name}'",
        )

    # Get or create transport
    transport: MCPTransport = getattr(request.app.state, "mcp_transport", None) or MCPTransport()
    start = time.monotonic()

    try:
        result = await transport.invoke(
            server=server,
            tool_name=body.tool_name,
            arguments=body.arguments,
        )
    except MCPTransportError as exc:
        duration_ms = (time.monotonic() - start) * 1000
        logger.warning(
            "Tool invocation failed: %s/%s: %s",
            body.server_name, body.tool_name, exc,
        )
        return ToolCallResponse(
            server_name=body.server_name,
            tool_name=body.tool_name,
            error=str(exc),
            duration_ms=round(duration_ms, 2),
        )

    duration_ms = (time.monotonic() - start) * 1000

    return ToolCallResponse(
        server_name=body.server_name,
        tool_name=body.tool_name,
        result=result,
        duration_ms=round(duration_ms, 2),
    )
