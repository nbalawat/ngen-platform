"""Shared fixtures for governance service tests.

Each test gets a fresh repository and engine — no state leakage between tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

import governance_service.routes as routes
from governance_service.app import create_app


@pytest.fixture()
def governance_app():
    """Create a fresh governance service app with clean state."""
    routes._repository = None
    routes._engine = None
    return create_app()


@pytest.fixture()
async def client(governance_app) -> AsyncIterator[httpx.AsyncClient]:
    """Direct httpx client for the governance service."""
    transport = httpx.ASGITransport(app=governance_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://governance"
    ) as c:
        yield c
