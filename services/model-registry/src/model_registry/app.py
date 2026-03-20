from __future__ import annotations

from fastapi import FastAPI

from model_registry.routes import router


def create_app() -> FastAPI:
    application = FastAPI(title="NGEN Model Registry", version="0.1.0")

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    application.include_router(router)
    return application


app = create_app()
