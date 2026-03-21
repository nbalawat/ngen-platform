"""FastAPI application for the MCP Manager service."""

from __future__ import annotations

from fastapi import FastAPI

from mcp_manager.routes import invoke_router, server_router, tool_router
from mcp_manager.transport import MCPTransport
from ngen_common.error_handlers import add_error_handlers
from ngen_common.events import add_event_bus
from ngen_common.observability import add_observability


def create_app(
    mcp_transport: MCPTransport | None = None,
) -> FastAPI:
    application = FastAPI(
        title="NGEN MCP Manager",
        version="0.1.0",
    )

    # MCP transport for tool invocation
    application.state.mcp_transport = mcp_transport or MCPTransport()

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    application.include_router(server_router)
    application.include_router(tool_router)
    application.include_router(invoke_router)
    add_error_handlers(application)
    add_observability(application, service_name="mcp-manager")
    add_event_bus(application, service_name="mcp-manager")
    return application


app = create_app()
