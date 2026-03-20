"""FastAPI application for the MCP Manager service."""

from __future__ import annotations

from fastapi import FastAPI

from mcp_manager.routes import invoke_router, server_router, tool_router


def create_app() -> FastAPI:
    application = FastAPI(
        title="NGEN MCP Manager",
        version="0.1.0",
    )

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    application.include_router(server_router)
    application.include_router(tool_router)
    application.include_router(invoke_router)
    return application


app = create_app()
