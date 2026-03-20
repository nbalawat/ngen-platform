"""FastAPI application for the governance service."""

from __future__ import annotations

from fastapi import FastAPI

from governance_service.routes import eval_router, router


def create_app() -> FastAPI:
    application = FastAPI(
        title="NGEN Governance Service",
        version="0.1.0",
    )

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    application.include_router(router)
    application.include_router(eval_router)
    return application


app = create_app()
