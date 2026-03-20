"""Base provider protocol and registry."""

from __future__ import annotations

from typing import Any, Protocol

import httpx


class LLMProvider(Protocol):
    """Protocol for LLM provider adapters.

    Each provider knows how to translate an OpenAI-compatible chat
    request into the provider's native format, call the upstream,
    and translate the response back to OpenAI-compatible format.
    """

    async def chat_completion(
        self,
        client: httpx.AsyncClient,
        upstream_url: str,
        body: dict[str, Any],
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request and return an OpenAI-compatible response."""
        ...

    async def native_request(
        self,
        client: httpx.AsyncClient,
        upstream_url: str,
        body: dict[str, Any],
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Send a request in the provider's native format."""
        ...


class ProviderRegistry:
    """Maps provider names to LLMProvider implementations."""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, name: str, provider: LLMProvider) -> None:
        self._providers[name] = provider

    def get(self, name: str) -> LLMProvider | None:
        return self._providers.get(name)

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())
