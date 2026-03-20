from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from tenant_service.infrastructure.database import Base


@pytest.fixture()
async def db_engine():
    """Create an async in-memory SQLite engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture()
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional async session tied to the in-memory DB."""
    session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture()
def app(db_engine):
    """Create the FastAPI application with an overridden DB dependency."""
    from tenant_service.api.app import create_app
    from tenant_service.infrastructure.database import get_db

    test_app = create_app()

    session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False
    )

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    test_app.dependency_overrides[get_db] = _override_get_db
    return test_app


@pytest.fixture()
async def client(app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client wired to the test FastAPI app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture()
def sample_org_payload() -> dict[str, Any]:
    """Valid payload for creating an organization."""
    return {
        "name": "Acme Corp",
        "slug": "acme-corp",
        "contact_email": "admin@acme.test",
        "tier": "FREE",
        "max_agents": 10,
        "max_teams": 5,
    }


@pytest.fixture()
def sample_team_payload() -> dict[str, Any]:
    """Valid payload for creating a team."""
    return {
        "name": "Backend Team",
        "slug": "backend-team",
    }


@pytest.fixture()
def sample_project_payload() -> dict[str, Any]:
    """Valid payload for creating a project."""
    return {
        "name": "Auth Service",
        "slug": "auth-service",
    }
