"""FastAPI application for the governance service."""

from __future__ import annotations

from fastapi import FastAPI

from governance_service.routes import eval_router, router
from ngen_common.error_handlers import add_error_handlers
from ngen_common.observability import add_observability


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
    add_error_handlers(application)
    add_observability(application, service_name="governance-service")
    return application


app = create_app()
