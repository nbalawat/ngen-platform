"""Cost tracker for the NGEN model gateway.

Tracks token usage and cost per tenant/model. When an event bus is
configured, cost events are published for downstream consumers
(metering service, audit trail, billing).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from ngen_common.events import EventBus


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
    """Tracks LLM usage costs per tenant.

    When an event_bus is provided, cost events are also published
    to the "cost.recorded" subject for downstream consumers.
    """

    def __init__(
        self,
        pricing: dict[str, tuple[float, float]] | None = None,
        event_bus: "EventBus | None" = None,
    ) -> None:
        self._pricing = pricing or DEFAULT_PRICING
        self._events: list[CostEvent] = []
        self._event_bus = event_bus

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

        # Publish to event bus if configured
        if self._event_bus is not None:
            self._publish_event(event)

        return event

    def _publish_event(self, event: CostEvent) -> None:
        """Fire-and-forget publish to the event bus."""
        from ngen_common.events import publish_cost_event

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                publish_cost_event(
                    self._event_bus,
                    tenant_id=event.tenant_id,
                    model=event.model,
                    prompt_tokens=event.prompt_tokens,
                    completion_tokens=event.completion_tokens,
                    total_cost=event.total_cost,
                    source="model-gateway",
                )
            )
        except RuntimeError:
            # No running loop — skip publishing (e.g., sync test context)
            pass

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
