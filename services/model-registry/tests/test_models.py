from __future__ import annotations

import pytest
from model_registry.models import (
    ModelCapability,
    ModelConfig,
    ModelConfigCreate,
    ModelConfigUpdate,
    ModelProvider,
)
from pydantic import ValidationError


class TestModelProvider:
    def test_provider_values(self):
        assert ModelProvider.ANTHROPIC == "ANTHROPIC"
        assert ModelProvider.OPENAI == "OPENAI"
        assert ModelProvider.GOOGLE == "GOOGLE"
        assert ModelProvider.AZURE == "AZURE"
        assert ModelProvider.LOCAL == "LOCAL"


class TestModelCapability:
    def test_capability_values(self):
        assert ModelCapability.STREAMING == "STREAMING"
        assert ModelCapability.TOOL_USE == "TOOL_USE"
        assert ModelCapability.VISION == "VISION"
        assert ModelCapability.THINKING == "THINKING"
        assert ModelCapability.STRUCTURED_OUTPUT == "STRUCTURED_OUTPUT"


class TestModelConfig:
    def test_create_with_defaults(self):
        model = ModelConfig(
            name="test-model",
            provider=ModelProvider.ANTHROPIC,
            endpoint="https://api.example.com",
        )
        assert model.name == "test-model"
        assert model.provider == ModelProvider.ANTHROPIC
        assert model.id is not None
        assert model.capabilities == []
        assert model.context_window == 200_000
        assert model.max_output_tokens == 16_000
        assert model.cost_per_m_input == 0.0
        assert model.cost_per_m_output == 0.0
        assert model.is_active is True
        assert model.created_at is not None
        assert model.updated_at is not None
        assert model.metadata == {}

    def test_create_with_all_fields(self):
        model = ModelConfig(
            name="gpt-4o",
            provider=ModelProvider.OPENAI,
            endpoint="https://api.openai.com/v1/chat/completions",
            capabilities=[ModelCapability.STREAMING, ModelCapability.VISION],
            context_window=128_000,
            max_output_tokens=4096,
            cost_per_m_input=5.0,
            cost_per_m_output=15.0,
            is_active=False,
            metadata={"region": "us-east-1"},
        )
        assert model.provider == ModelProvider.OPENAI
        assert len(model.capabilities) == 2
        assert model.context_window == 128_000
        assert model.is_active is False
        assert model.metadata["region"] == "us-east-1"

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            ModelConfig(
                name="ab",
                provider=ModelProvider.ANTHROPIC,
                endpoint="https://api.example.com",
            )

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            ModelConfig(
                name="x" * 101,
                provider=ModelProvider.ANTHROPIC,
                endpoint="https://api.example.com",
            )

    def test_invalid_provider(self):
        with pytest.raises(ValidationError):
            ModelConfig(
                name="test-model",
                provider="INVALID",
                endpoint="https://api.example.com",
            )

    def test_unique_ids(self):
        m1 = ModelConfig(
            name="model-a",
            provider=ModelProvider.ANTHROPIC,
            endpoint="https://a.example.com",
        )
        m2 = ModelConfig(
            name="model-b",
            provider=ModelProvider.OPENAI,
            endpoint="https://b.example.com",
        )
        assert m1.id != m2.id


class TestModelConfigCreate:
    def test_create_dto(self):
        dto = ModelConfigCreate(
            name="claude-opus-4-6",
            provider=ModelProvider.ANTHROPIC,
            endpoint="https://api.anthropic.com/v1/messages",
        )
        assert dto.name == "claude-opus-4-6"
        assert not hasattr(dto, "id")
        assert not hasattr(dto, "created_at")


class TestModelConfigUpdate:
    def test_all_fields_optional(self):
        update = ModelConfigUpdate()
        data = update.model_dump(exclude_unset=True)
        assert data == {}

    def test_partial_update(self):
        update = ModelConfigUpdate(name="renamed-model", is_active=False)
        data = update.model_dump(exclude_unset=True)
        assert data == {"name": "renamed-model", "is_active": False}
