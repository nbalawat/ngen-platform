"""Model Gateway FastAPI application.

Multi-provider proxy that routes requests to upstream LLM providers
(mock, Anthropic, Ollama) with rate limiting and cost tracking.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from model_gateway.config import settings
from model_gateway.cost_tracker import CostTracker
from model_gateway.providers.anthropic import AnthropicProvider
from model_gateway.providers.base import ProviderRegistry
from model_gateway.providers.openai_compat import OpenAICompatProvider
from model_gateway.rate_limiter import RateLimiter
from model_gateway.redis_rate_limiter import create_rate_limiter
from model_gateway.model_sync import ModelSyncSubscriber
from model_gateway.router import ModelRouter
from ngen_common.cors import add_cors
from ngen_common.auth import add_auth
from ngen_common.auth_config import make_auth_config
from ngen_common.error_handlers import add_error_handlers
from ngen_common.events import EventBus, add_event_bus
from ngen_common.observability import add_observability

logger = logging.getLogger(__name__)


def _default_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register("mock", OpenAICompatProvider())
    registry.register("ollama", OpenAICompatProvider())
    registry.register("anthropic", AnthropicProvider())
    return registry


def _auto_register_models(router: ModelRouter) -> None:
    """Register models from config on startup."""
    # Mock models (always available)
    router.register("mock-model", settings.DEFAULT_UPSTREAM_URL, provider="mock")
    router.register("mock-model-fast", settings.DEFAULT_UPSTREAM_URL, provider="mock")

    # Anthropic models (if API key is configured)
    if settings.ANTHROPIC_API_KEY:
        for model_id in ("claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"):
            router.register(
                model_id,
                settings.ANTHROPIC_API_URL,
                provider="anthropic",
                api_key=settings.ANTHROPIC_API_KEY,
            )
        logger.info("Registered Anthropic models (claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5)")

    # Ollama models — try to auto-discover from running Ollama instance
    ollama_url = settings.OLLAMA_URL
    try:
        import httpx as _httpx

        resp = _httpx.get(f"{ollama_url}/api/tags", timeout=3.0)
        if resp.status_code == 200:
            for m in resp.json().get("models", []):
                model_name = m["name"]
                # Register both the full name (e.g. "llama3.2:latest")
                # and the short name (e.g. "llama3.2")
                router.register(model_name, ollama_url, provider="ollama")
                short_name = model_name.split(":")[0]
                if short_name != model_name:
                    router.register(short_name, ollama_url, provider="ollama")
            logger.info(
                "Auto-discovered %d Ollama models at %s",
                len(resp.json().get("models", [])),
                ollama_url,
            )
        else:
            logger.warning("Ollama returned %d at %s", resp.status_code, ollama_url)
    except Exception:
        logger.info("Ollama not reachable at %s — skipping auto-discovery", ollama_url)


def create_app(
    router: ModelRouter | None = None,
    rate_limiter: RateLimiter | None = None,
    cost_tracker: CostTracker | None = None,
    http_client: httpx.AsyncClient | None = None,
    provider_registry: ProviderRegistry | None = None,
    auto_register: bool = False,
    event_bus: EventBus | None = None,
) -> FastAPI:
    app = FastAPI(title="NGEN Model Gateway", version="0.1.0")

    # Wire event bus (reads NATS_URL from env if not provided)
    import asyncio
    _bus = event_bus
    if _bus is None:
        _bus_holder: list[EventBus] = []
        # Use add_event_bus to create and register lifecycle hooks
        # This is deferred to startup, but we need the bus for CostTracker now
        # So we create it eagerly via the helper
        import os
        nats_url = os.environ.get("NATS_URL", "")
        if nats_url:
            from ngen_common.events import NATSEventBus
            _bus = NATSEventBus(url=nats_url, source="model-gateway")
        else:
            from ngen_common.events import InMemoryEventBus
            _bus = InMemoryEventBus()

    app.state.event_bus = _bus

    model_router = router or ModelRouter()

    # Model sync subscriber — auto-updates router from registry events
    sync_subscriber = ModelSyncSubscriber(
        event_bus=_bus,
        model_router=model_router,
        default_upstream_url=settings.DEFAULT_UPSTREAM_URL,
    )
    app.state.model_sync = sync_subscriber

    @app.on_event("startup")
    async def _connect_event_bus() -> None:
        await app.state.event_bus.connect()
        await sync_subscriber.start()
        logger.info("Event bus connected for model-gateway")

    @app.on_event("shutdown")
    async def _disconnect_event_bus() -> None:
        await sync_subscriber.stop()
        await app.state.event_bus.disconnect()
        logger.info("Event bus disconnected for model-gateway")
    limiter = rate_limiter or create_rate_limiter(
        rpm=settings.RATE_LIMIT_RPM,
        tpm=settings.RATE_LIMIT_TPM,
    )
    tracker = cost_tracker or CostTracker(event_bus=_bus)
    providers = provider_registry or _default_provider_registry()

    if auto_register:
        _auto_register_models(model_router)

    # Expose on app state for test access and extensibility
    app.state.model_router = model_router
    app.state.rate_limiter = limiter
    app.state.cost_tracker = tracker
    app.state.http_client = http_client
    app.state.provider_registry = providers

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.post("/v1/chat/completions")
    async def proxy_chat_completions(request: Request) -> JSONResponse:
        body: dict[str, Any] = await request.json()
        model_id = body.get("model", settings.DEFAULT_MODEL)
        tenant_id = request.headers.get("x-tenant-id", "default")

        # Rate limit check
        if not limiter.check_request(tenant_id):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded (RPM)",
            )

        # Resolve upstream
        route = model_router.resolve(model_id)
        if route is None:
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model_id}' not registered",
            )

        # Get the provider for this route
        provider = providers.get(route.provider)
        if provider is None:
            raise HTTPException(
                status_code=500,
                detail=f"Provider '{route.provider}' not configured",
            )

        # Get or create HTTP client
        upstream_client = app.state.http_client
        should_close = False
        if upstream_client is None:
            upstream_client = httpx.AsyncClient(timeout=60.0)
            should_close = True

        try:
            data = await provider.chat_completion(
                client=upstream_client,
                upstream_url=route.upstream_url,
                body=body,
                api_key=route.api_key or None,
            )
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Upstream error: {exc.response.text}",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        finally:
            if should_close:
                await upstream_client.aclose()

        # Track cost
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        if prompt_tokens or completion_tokens:
            limiter.check_tokens(
                tenant_id, prompt_tokens + completion_tokens
            )
            tracker.record(
                tenant_id=tenant_id,
                model=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        return JSONResponse(
            content=data,
            headers={
                "x-ratelimit-remaining-requests": str(
                    limiter.remaining_rpm(tenant_id)
                ),
                "x-ratelimit-remaining-tokens": str(
                    limiter.remaining_tpm(tenant_id)
                ),
            },
        )

    @app.post("/v1/messages")
    async def proxy_anthropic_messages(request: Request) -> JSONResponse:
        """Native Anthropic Messages API passthrough.

        Allows calling Anthropic models in their native format
        without OpenAI translation.
        """
        body: dict[str, Any] = await request.json()
        model_id = body.get("model", "")
        tenant_id = request.headers.get("x-tenant-id", "default")

        if not limiter.check_request(tenant_id):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded (RPM)",
            )

        route = model_router.resolve(model_id)
        if route is None:
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model_id}' not registered",
            )

        if route.provider != "anthropic":
            raise HTTPException(
                status_code=400,
                detail=f"Model '{model_id}' is not an Anthropic model. Use /v1/chat/completions instead.",
            )

        provider = providers.get("anthropic")
        if provider is None:
            raise HTTPException(
                status_code=500,
                detail="Anthropic provider not configured",
            )

        upstream_client = app.state.http_client
        should_close = False
        if upstream_client is None:
            upstream_client = httpx.AsyncClient(timeout=60.0)
            should_close = True

        try:
            data = await provider.native_request(
                client=upstream_client,
                upstream_url=route.upstream_url,
                body=body,
                api_key=route.api_key or None,
            )
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Upstream error: {exc.response.text}",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        finally:
            if should_close:
                await upstream_client.aclose()

        # Track cost from Anthropic usage format
        usage = data.get("usage", {})
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)

        if prompt_tokens or completion_tokens:
            limiter.check_tokens(
                tenant_id, prompt_tokens + completion_tokens
            )
            tracker.record(
                tenant_id=tenant_id,
                model=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        return JSONResponse(content=data)

    @app.get("/v1/usage/{tenant_id}")
    async def get_usage(tenant_id: str) -> dict:
        return tracker.get_tenant_usage(tenant_id)

    @app.get("/v1/models")
    async def list_models() -> dict:
        routes = model_router.list_models()
        return {
            "object": "list",
            "data": [
                {
                    "id": r.model_id,
                    "object": "model",
                    "owned_by": r.provider,
                }
                for r in routes
            ],
        }

    add_error_handlers(app)
    add_cors(app)
    add_observability(app, service_name="model-gateway")
    add_auth(app, make_auth_config())
    return app


app = create_app(auto_register=True)
