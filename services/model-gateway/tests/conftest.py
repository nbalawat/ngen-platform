from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest

from ngen_mock_llm import CannedStrategy, create_mock_llm_app

from model_gateway.app import create_app
from model_gateway.cost_tracker import CostTracker
from model_gateway.providers.base import ProviderRegistry
from model_gateway.providers.openai_compat import OpenAICompatProvider
from model_gateway.rate_limiter import RateLimiter
from model_gateway.router import ModelRouter


@pytest.fixture()
def mock_llm_app():
    """Standalone mock LLM server."""
    return create_mock_llm_app(strategy=CannedStrategy("Mock reply."))


@pytest.fixture()
def model_router() -> ModelRouter:
    router = ModelRouter()
    router.register("mock-model", "http://mock-llm", provider="mock")
    router.register(
        "mock-model-fast", "http://mock-llm", provider="mock"
    )
    return router


@pytest.fixture()
def rate_limiter() -> RateLimiter:
    return RateLimiter(rpm=5, tpm=1000)


@pytest.fixture()
def cost_tracker() -> CostTracker:
    return CostTracker()


@pytest.fixture()
def provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register("mock", OpenAICompatProvider())
    return registry


@pytest.fixture()
def upstream_client(mock_llm_app) -> httpx.AsyncClient:
    """HTTP client that routes to the mock LLM app."""
    transport = httpx.ASGITransport(app=mock_llm_app)
    return httpx.AsyncClient(transport=transport)


@pytest.fixture()
def gateway_app(
    model_router: ModelRouter,
    rate_limiter: RateLimiter,
    cost_tracker: CostTracker,
    upstream_client: httpx.AsyncClient,
    provider_registry: ProviderRegistry,
) -> object:
    return create_app(
        router=model_router,
        rate_limiter=rate_limiter,
        cost_tracker=cost_tracker,
        http_client=upstream_client,
        provider_registry=provider_registry,
    )


@pytest.fixture()
async def client(
    gateway_app,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=gateway_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://gateway"
    ) as ac:
        yield ac
