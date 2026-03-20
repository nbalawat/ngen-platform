"""Pydantic request/response models for the Workflow Engine API."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class WorkflowRunStatus(StrEnum):
    """Status of a workflow run."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowRunRequest(BaseModel):
    """Request body for starting a workflow run."""

    workflow_yaml: str = Field(..., description="Raw YAML string of a WorkflowCRD")
    input_data: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


class WorkflowRunResponse(BaseModel):
    """Response body for a workflow run."""

    run_id: str
    status: WorkflowRunStatus
    result: dict[str, Any] | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    created_at: float
    updated_at: float
