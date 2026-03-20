from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
from model_registry.app import create_app
from model_registry.repository import ModelRepository
from model_registry.routes import get_repository


@pytest.fixture()
def app():
    """Create the FastAPI application with a fresh repository."""
    test_app = create_app()
    repo = ModelRepository()
    test_app.dependency_overrides[get_repository] = lambda: repo
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
def sample_model_payload() -> dict[str, Any]:
    """Valid payload for creating a model configuration."""
    return {
        "name": "claude-opus-4-6",
        "provider": "ANTHROPIC",
        "endpoint": "https://api.anthropic.com/v1/messages",
        "capabilities": ["STREAMING", "TOOL_USE", "VISION"],
        "context_window": 200000,
        "max_output_tokens": 16000,
        "cost_per_m_input": 15.0,
        "cost_per_m_output": 75.0,
    }
