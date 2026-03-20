"""OpenAI-compatible provider (mock LLM, Ollama, vLLM, etc.)."""

from __future__ import annotations

from typing import Any

import httpx


class OpenAICompatProvider:
    """Provider for any upstream that speaks the OpenAI chat completions API.

    Works with: mock-llm, Ollama, vLLM, LiteLLM, LocalAI, etc.
    """

    async def chat_completion(
        self,
        client: httpx.AsyncClient,
        upstream_url: str,
        body: dict[str, Any],
        api_key: str | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        resp = await client.post(
            f"{upstream_url}/v1/chat/completions",
            json=body,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def native_request(
        self,
        client: httpx.AsyncClient,
        upstream_url: str,
        body: dict[str, Any],
        api_key: str | None = None,
    ) -> dict[str, Any]:
        # For OpenAI-compatible providers, native format IS chat completions
        return await self.chat_completion(client, upstream_url, body, api_key)
