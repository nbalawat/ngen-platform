"""Anthropic provider — uses the official Anthropic Python SDK.

Translates between OpenAI chat format and Anthropic Messages API,
and also supports native passthrough.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
from anthropic import AsyncAnthropic


def openai_to_anthropic(body: dict[str, Any]) -> dict[str, Any]:
    """Translate an OpenAI chat completion request to Anthropic Messages format."""
    messages = body.get("messages", [])

    # Extract system message (Anthropic puts it as a top-level field)
    system: str | None = None
    anthropic_messages: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "system":
            system = content
        elif role == "user":
            anthropic_messages.append({"role": "user", "content": content})
        elif role == "assistant":
            anthropic_messages.append({"role": "assistant", "content": content})

    result: dict[str, Any] = {
        "model": body.get("model", "claude-sonnet-4-6"),
        "max_tokens": body.get("max_tokens", 4096),
        "messages": anthropic_messages,
    }

    if system:
        result["system"] = system

    # Map temperature if provided
    if "temperature" in body:
        result["temperature"] = body["temperature"]

    # Map top_p if provided
    if "top_p" in body:
        result["top_p"] = body["top_p"]

    # Map stop sequences
    if "stop" in body:
        stop = body["stop"]
        if isinstance(stop, str):
            result["stop_sequences"] = [stop]
        elif isinstance(stop, list):
            result["stop_sequences"] = stop

    return result


def anthropic_response_to_openai(
    message: Any,
    model: str,
) -> dict[str, Any]:
    """Translate an Anthropic Message response object to OpenAI chat completion format."""
    # Handle both SDK Message objects and raw dicts
    if isinstance(message, dict):
        return _anthropic_dict_to_openai(message, model)

    # SDK Message object
    text_parts = []
    for block in message.content:
        if block.type == "text":
            text_parts.append(block.text)

    assistant_content = "\n".join(text_parts) if text_parts else ""

    finish_reason_map = {
        "end_turn": "stop",
        "max_tokens": "length",
        "stop_sequence": "stop",
        "tool_use": "tool_calls",
    }
    finish_reason = finish_reason_map.get(message.stop_reason, "stop")

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": assistant_content,
                },
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": message.usage.input_tokens,
            "completion_tokens": message.usage.output_tokens,
            "total_tokens": message.usage.input_tokens + message.usage.output_tokens,
        },
    }


def _anthropic_dict_to_openai(
    anthropic_resp: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    """Translate a raw Anthropic dict response to OpenAI format (for testing)."""
    content_blocks = anthropic_resp.get("content", [])
    text_parts = []
    for block in content_blocks:
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))

    assistant_content = "\n".join(text_parts) if text_parts else ""

    stop_reason = anthropic_resp.get("stop_reason", "end_turn")
    finish_reason_map = {
        "end_turn": "stop",
        "max_tokens": "length",
        "stop_sequence": "stop",
        "tool_use": "tool_calls",
    }
    finish_reason = finish_reason_map.get(stop_reason, "stop")

    usage = anthropic_resp.get("usage", {})
    prompt_tokens = usage.get("input_tokens", 0)
    completion_tokens = usage.get("output_tokens", 0)

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": assistant_content,
                },
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


# Keep the old name as an alias for backward compat with tests
anthropic_to_openai = _anthropic_dict_to_openai


class AnthropicProvider:
    """Provider for the Anthropic Messages API using the official SDK.

    Uses `anthropic.AsyncAnthropic` for all API calls, which handles:
    - Auth headers (x-api-key, anthropic-version)
    - Automatic retries on 429/5xx (2 retries by default)
    - Typed error classes (RateLimitError, AuthenticationError, etc.)
    - Response parsing into Pydantic models
    """

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        # SDK clients are created per-request with the route's API key
        # to support multi-tenant key isolation
        self._clients: dict[str, AsyncAnthropic] = {}
        self._http_client = http_client  # injectable for testing

    def _get_client(self, api_key: str, base_url: str) -> AsyncAnthropic:
        """Get or create an AsyncAnthropic client for the given key/url pair."""
        cache_key = f"{api_key[:8]}:{base_url}"
        if cache_key not in self._clients:
            kwargs: dict[str, Any] = {
                "api_key": api_key,
                "base_url": base_url,
                "max_retries": 2,
            }
            if self._http_client is not None:
                kwargs["http_client"] = self._http_client
            self._clients[cache_key] = AsyncAnthropic(**kwargs)
        return self._clients[cache_key]

    async def chat_completion(
        self,
        client: httpx.AsyncClient,
        upstream_url: str,
        body: dict[str, Any],
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Translate OpenAI format -> Anthropic SDK call -> translate back."""
        if not api_key:
            raise ValueError("Anthropic API key is required")

        params = openai_to_anthropic(body)
        model = params.pop("model")
        messages = params.pop("messages")

        sdk_client = self._get_client(api_key, upstream_url)

        message = await sdk_client.messages.create(
            model=model,
            messages=messages,
            **params,
        )

        return anthropic_response_to_openai(message, model)

    async def native_request(
        self,
        client: httpx.AsyncClient,
        upstream_url: str,
        body: dict[str, Any],
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Send a request in Anthropic's native Messages API format using the SDK."""
        if not api_key:
            raise ValueError("Anthropic API key is required")

        sdk_client = self._get_client(api_key, upstream_url)

        # Copy to avoid mutating the caller's dict
        params = dict(body)
        model = params.pop("model", "claude-sonnet-4-6")
        messages = params.pop("messages", [])
        max_tokens = params.pop("max_tokens", 4096)

        message = await sdk_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            **params,
        )

        return message.to_dict()
