from __future__ import annotations

from fastapi import FastAPI

from model_registry.routes import router
from ngen_common.auth import add_auth
from ngen_common.auth_config import make_auth_config
from ngen_common.error_handlers import add_error_handlers
from ngen_common.events import add_event_bus
from ngen_common.observability import add_observability


def create_app() -> FastAPI:
    application = FastAPI(title="NGEN Model Registry", version="0.1.0")

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    application.include_router(router)
    add_error_handlers(application)
    add_observability(application, service_name="model-registry")
    add_auth(application, make_auth_config())
    add_event_bus(application, service_name="model-registry")
    return application


app = create_app()
