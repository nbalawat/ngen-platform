"""Shared fixtures for NGEN SDK tests.

Each test gets fresh service apps with clean state.
Uses real ASGI transports — no mocks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from ngen_sdk.client import NgenClient


@pytest.fixture()
def governance_app():
    import governance_service.routes as gov_routes
    from governance_service.app import create_app

    gov_routes._repository = None
    gov_routes._engine = None
    return create_app()


@pytest.fixture()
def mcp_app():
    import mcp_manager.routes as mcp_routes
    from mcp_manager.app import create_app

    mcp_routes._repository = None
    return create_app()


@pytest.fixture()
async def governance_client(governance_app) -> AsyncIterator[NgenClient]:
    transport = httpx.ASGITransport(app=governance_app)
    http = httpx.AsyncClient(transport=transport, base_url="http://governance")
    async with NgenClient(
        governance_url="http://governance", http_client=http
    ) as client:
        yield client


@pytest.fixture()
async def mcp_client(mcp_app) -> AsyncIterator[NgenClient]:
    transport = httpx.ASGITransport(app=mcp_app)
    http = httpx.AsyncClient(transport=transport, base_url="http://mcp")
    async with NgenClient(mcp_url="http://mcp", http_client=http) as client:
        yield client
