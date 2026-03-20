from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest

from ngen_mock_llm import create_mock_llm_app


@pytest.fixture()
def mock_llm_app():
    return create_mock_llm_app()


@pytest.fixture()
async def client(mock_llm_app) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=mock_llm_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as ac:
        yield ac
