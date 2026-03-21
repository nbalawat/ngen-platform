from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from tenant_service.api.routes import router
from tenant_service.infrastructure.database import Base, _get_engine
from ngen_common.auth import add_auth
from ngen_common.auth_config import make_auth_config
from ngen_common.error_handlers import add_error_handlers
from ngen_common.events import add_event_bus
from ngen_common.observability import add_observability


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create tables on startup (dev convenience — use Alembic in production)."""
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="NGEN Tenant Service", version="0.1.0", lifespan=lifespan
    )

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    application.include_router(router)
    add_error_handlers(application)
    add_observability(application, service_name="tenant-service")
    add_auth(application, make_auth_config())
    add_event_bus(application, service_name="tenant-service")
    return application


app = create_app()
