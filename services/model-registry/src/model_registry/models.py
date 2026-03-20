from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ModelProvider(StrEnum):
    ANTHROPIC = "ANTHROPIC"
    OPENAI = "OPENAI"
    GOOGLE = "GOOGLE"
    AZURE = "AZURE"
    LOCAL = "LOCAL"


class ModelCapability(StrEnum):
    STREAMING = "STREAMING"
    TOOL_USE = "TOOL_USE"
    VISION = "VISION"
    THINKING = "THINKING"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"


def _utc_now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Full model configuration (stored / returned)
# ---------------------------------------------------------------------------


class ModelConfig(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=3, max_length=100)
    provider: ModelProvider
    endpoint: str
    capabilities: list[ModelCapability] = Field(default_factory=list)
    context_window: int = 200_000
    max_output_tokens: int = 16_000
    cost_per_m_input: float = 0.0
    cost_per_m_output: float = 0.0
    is_active: bool = True
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Create / Update DTOs
# ---------------------------------------------------------------------------


class ModelConfigCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    provider: ModelProvider
    endpoint: str
    capabilities: list[ModelCapability] = Field(default_factory=list)
    context_window: int = 200_000
    max_output_tokens: int = 16_000
    cost_per_m_input: float = 0.0
    cost_per_m_output: float = 0.0
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=100)
    provider: ModelProvider | None = None
    endpoint: str | None = None
    capabilities: list[ModelCapability] | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    cost_per_m_input: float | None = None
    cost_per_m_output: float | None = None
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None
