"""Mock LLM server — OpenAI-compatible chat completions endpoint."""

from __future__ import annotations

from fastapi import FastAPI

from ngen_mock_llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    Usage,
)
from ngen_mock_llm.strategies import CannedStrategy, ResponseStrategy


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


def create_mock_llm_app(
    strategy: ResponseStrategy | None = None,
) -> FastAPI:
    """Create a FastAPI app that mimics the OpenAI chat completions API.

    Args:
        strategy: Response strategy to use. Defaults to CannedStrategy.
    """
    app = FastAPI(title="NGEN Mock LLM Provider", version="0.1.0")
    strat = strategy or CannedStrategy()

    # Allow swapping strategy at runtime (useful in tests)
    app.state.strategy = strat  # type: ignore[attr-defined]

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.post("/v1/chat/completions")
    async def chat_completions(
        request: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        current_strategy: ResponseStrategy = app.state.strategy  # type: ignore[attr-defined]
        response_msg = current_strategy.generate(request)

        prompt_text = " ".join(
            m.content or "" for m in request.messages
        )
        prompt_tokens = _estimate_tokens(prompt_text)
        completion_tokens = _estimate_tokens(response_msg.content or "")

        finish_reason = (
            "tool_calls" if response_msg.tool_calls else "stop"
        )

        return ChatCompletionResponse(
            model=request.model,
            choices=[
                Choice(
                    message=response_msg,
                    finish_reason=finish_reason,
                )
            ],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    @app.get("/v1/models")
    async def list_models() -> dict:
        return {
            "object": "list",
            "data": [
                {
                    "id": "mock-model",
                    "object": "model",
                    "created": 1700000000,
                    "owned_by": "ngen-mock",
                },
                {
                    "id": "mock-model-fast",
                    "object": "model",
                    "created": 1700000000,
                    "owned_by": "ngen-mock",
                },
            ],
        }

    return app
