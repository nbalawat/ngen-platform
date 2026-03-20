from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from model_registry.models import (
    ModelConfig,
    ModelConfigCreate,
    ModelConfigUpdate,
    ModelProvider,
)


class ModelRepository:
    """In-memory repository for model configurations."""

    def __init__(self) -> None:
        self._store: dict[UUID, ModelConfig] = {}

    def create(self, data: ModelConfigCreate) -> ModelConfig:
        """Register a new model configuration.

        Raises ValueError if a model with the same name already exists.
        """
        for existing in self._store.values():
            if existing.name == data.name:
                msg = f"Model with name '{data.name}' already exists"
                raise ValueError(msg)

        model = ModelConfig(**data.model_dump())
        self._store[model.id] = model
        return model

    def get(self, model_id: UUID) -> ModelConfig | None:
        return self._store.get(model_id)

    def get_by_name(self, name: str) -> ModelConfig | None:
        for model in self._store.values():
            if model.name == name:
                return model
        return None

    def list(self, *, provider: ModelProvider | None = None) -> list[ModelConfig]:
        models = list(self._store.values())
        if provider is not None:
            models = [m for m in models if m.provider == provider]
        return models

    def update(
        self, model_id: UUID, data: ModelConfigUpdate
    ) -> ModelConfig | None:
        existing = self._store.get(model_id)
        if existing is None:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # Check for duplicate name if name is being changed
        if "name" in update_data and update_data["name"] != existing.name:
            for other in self._store.values():
                if other.id != model_id and other.name == update_data["name"]:
                    msg = f"Model with name '{update_data['name']}' already exists"
                    raise ValueError(msg)

        if not update_data:
            return existing

        update_data["updated_at"] = datetime.now(UTC)
        updated = existing.model_copy(update=update_data)
        self._store[model_id] = updated
        return updated

    def delete(self, model_id: UUID) -> bool:
        return self._store.pop(model_id, None) is not None
