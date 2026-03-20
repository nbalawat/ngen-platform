from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from model_registry.models import (
    ModelConfig,
    ModelConfigCreate,
    ModelConfigUpdate,
    ModelProvider,
)
from model_registry.repository import ModelRepository

router = APIRouter(prefix="/api/v1")

_repository: ModelRepository | None = None


def get_repository() -> ModelRepository:
    """Return the singleton ModelRepository instance."""
    global _repository
    if _repository is None:
        _repository = ModelRepository()
    return _repository


RepoDep = Annotated[ModelRepository, Depends(get_repository)]


# ---------------------------------------------------------------------------
# Model CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/models",
    response_model=ModelConfig,
    status_code=status.HTTP_201_CREATED,
)
async def register_model(body: ModelConfigCreate, repo: RepoDep) -> ModelConfig:
    try:
        return repo.create(body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get("/models", response_model=list[ModelConfig])
async def list_models(
    repo: RepoDep,
    provider: ModelProvider | None = None,
) -> list[ModelConfig]:
    return repo.list(provider=provider)


@router.get("/models/{model_id}", response_model=ModelConfig)
async def get_model(model_id: UUID, repo: RepoDep) -> ModelConfig:
    model = repo.get(model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )
    return model


@router.get("/models/by-name/{name}", response_model=ModelConfig)
async def get_model_by_name(name: str, repo: RepoDep) -> ModelConfig:
    model = repo.get_by_name(name)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model with name '{name}' not found",
        )
    return model


@router.patch("/models/{model_id}", response_model=ModelConfig)
async def update_model(
    model_id: UUID, body: ModelConfigUpdate, repo: RepoDep
) -> ModelConfig:
    try:
        model = repo.update(model_id, body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )
    return model


@router.delete(
    "/models/{model_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_model(model_id: UUID, repo: RepoDep) -> None:
    deleted = repo.delete(model_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )
