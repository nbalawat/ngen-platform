"""FastAPI routes for the Workflow Engine service."""

from __future__ import annotations

import asyncio
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request

from ngen_framework_core.crd import parse_crd

from workflow_engine.engine import WorkflowEngine
from workflow_engine.errors import WorkflowNotFoundError
from workflow_engine.models import WorkflowRunRequest, WorkflowRunResponse, WorkflowRunStatus

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _get_engine(request: Request) -> WorkflowEngine:
    return request.app.state.engine


@router.post("/run", response_model=WorkflowRunResponse)
async def run_workflow(body: WorkflowRunRequest, request: Request) -> WorkflowRunResponse:
    """Start a new workflow run."""
    engine = _get_engine(request)

    # Parse the workflow YAML into a WorkflowCRD
    try:
        raw = yaml.safe_load(body.workflow_yaml)
        workflow = parse_crd(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid workflow YAML: {exc}") from exc

    if workflow.__class__.__name__ != "WorkflowCRD":
        raise HTTPException(
            status_code=400,
            detail=f"Expected kind 'Workflow', got '{raw.get('kind', 'unknown')}'"
        )

    # Run the workflow and collect events
    events: list[dict[str, Any]] = []
    async for event in engine.run_workflow(
        workflow=workflow,
        input_data=body.input_data,
        session_id=body.session_id,
    ):
        events.append({
            "type": event.type.value,
            "data": event.data,
            "agent_name": event.agent_name,
        })

    # Get the run to return its status
    runs = engine.list_runs()
    run = runs[-1] if runs else None

    return WorkflowRunResponse(
        run_id=run.run_id if run else "unknown",
        status=run.status if run else WorkflowRunStatus.FAILED,
        result=run.result if run else None,
        events=events,
        error=run.error if run else None,
        created_at=run.created_at if run else 0,
        updated_at=run.updated_at if run else 0,
    )


@router.get("/runs", response_model=list[WorkflowRunResponse])
async def list_runs(
    request: Request, status: WorkflowRunStatus | None = None
) -> list[WorkflowRunResponse]:
    """List all workflow runs, optionally filtered by status."""
    engine = _get_engine(request)
    runs = engine.list_runs(status=status)
    return [
        WorkflowRunResponse(
            run_id=r.run_id,
            status=r.status,
            result=r.result,
            events=[
                {"type": e.type.value, "data": e.data, "agent_name": e.agent_name}
                for e in r.events
            ],
            error=r.error,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=WorkflowRunResponse)
async def get_run(run_id: str, request: Request) -> WorkflowRunResponse:
    """Get the status of a workflow run."""
    engine = _get_engine(request)
    try:
        run = engine.get_run(run_id)
    except WorkflowNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return WorkflowRunResponse(
        run_id=run.run_id,
        status=run.status,
        result=run.result,
        events=[
            {"type": e.type.value, "data": e.data, "agent_name": e.agent_name}
            for e in run.events
        ],
        error=run.error,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.post("/runs/{run_id}/approve")
async def approve_run(run_id: str, request: Request) -> dict[str, Any]:
    """Approve a workflow run that is waiting for human approval."""
    engine = _get_engine(request)
    try:
        engine.get_run(run_id)
    except WorkflowNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    approved = engine.approve_run(run_id)
    if not approved:
        raise HTTPException(
            status_code=409, detail=f"Run '{run_id}' is not waiting for approval"
        )
    return {"run_id": run_id, "approved": True}


@router.delete("/runs/{run_id}")
async def cancel_run(run_id: str, request: Request) -> dict[str, Any]:
    """Cancel a running workflow."""
    engine = _get_engine(request)
    try:
        engine.get_run(run_id)
    except WorkflowNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    cancelled = engine.cancel_run(run_id)
    if not cancelled:
        raise HTTPException(
            status_code=409, detail=f"Run '{run_id}' cannot be cancelled"
        )
    return {"run_id": run_id, "cancelled": True}
