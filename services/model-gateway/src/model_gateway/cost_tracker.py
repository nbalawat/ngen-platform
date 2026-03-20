"""In-memory cost tracker for the Crawl phase.

Tracks token usage and cost per tenant/model. In Walk phase,
events will be published to NATS for the metering service.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from uuid import uuid4


# Default pricing per 1M tokens (input_price, output_price) in dollars
DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    # Mock models
    "mock-model": (5.00, 25.00),
    "mock-model-fast": (1.00, 5.00),
    # Anthropic models
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # Ollama models (local — no API cost)
    "llama3.2": (0.0, 0.0),
    "llama3.1": (0.0, 0.0),
    "mistral": (0.0, 0.0),
    "codellama": (0.0, 0.0),
    "phi3": (0.0, 0.0),
    "gemma2": (0.0, 0.0),
    "qwen2.5": (0.0, 0.0),
    "deepseek-r1": (0.0, 0.0),
}


@dataclass
class CostEvent:
    id: str = field(default_factory=lambda: uuid4().hex)
    tenant_id: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = 0.0
    timestamp: float = field(default_factory=time.time)


class CostTracker:
    """Tracks LLM usage costs per tenant."""

    def __init__(
        self,
        pricing: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self._pricing = pricing or DEFAULT_PRICING
        self._events: list[CostEvent] = []

    def record(
        self,
        tenant_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> CostEvent:
        """Record a usage event and calculate cost."""
        input_price, output_price = self._pricing.get(
            model, (0.0, 0.0)
        )
        input_cost = (prompt_tokens / 1_000_000) * input_price
        output_cost = (completion_tokens / 1_000_000) * output_price

        event = CostEvent(
            tenant_id=tenant_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=input_cost + output_cost,
        )
        self._events.append(event)
        return event

    def get_tenant_usage(
        self, tenant_id: str
    ) -> dict[str, float | int]:
        """Get aggregated usage for a tenant."""
        total_tokens = 0
        total_cost = 0.0
        request_count = 0
        for e in self._events:
            if e.tenant_id == tenant_id:
                total_tokens += e.total_tokens
                total_cost += e.total_cost
                request_count += 1
        return {
            "tenant_id": tenant_id,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 6),
            "request_count": request_count,
        }

    def get_all_events(self) -> list[CostEvent]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()
