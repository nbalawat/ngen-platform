"""FastAPI routes for the Workflow Engine service."""

from __future__ import annotations

import asyncio
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from ngen_framework_core.crd import WorkflowCRD, parse_crd
from ngen_framework_core.protocols import AgentEventType

from workflow_engine.engine import WorkflowEngine
from workflow_engine.errors import WorkflowNotFoundError
from workflow_engine.models import WorkflowRunRequest, WorkflowRunResponse, WorkflowRunStatus
from workflow_engine.sse import format_keepalive, format_sse

router = APIRouter(prefix="/workflows", tags=["workflows"])

KEEPALIVE_INTERVAL = 15.0  # seconds


def _get_engine(request: Request) -> WorkflowEngine:
    return request.app.state.engine


def _parse_workflow(body: WorkflowRunRequest) -> WorkflowCRD:
    """Parse and validate a WorkflowCRD from the request body.

    Raises HTTPException(400) on invalid YAML or wrong CRD kind.
    """
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
    return workflow


@router.post("/run", response_model=WorkflowRunResponse)
async def run_workflow(body: WorkflowRunRequest, request: Request) -> WorkflowRunResponse:
    """Start a new workflow run (blocking — returns all events at once)."""
    engine = _get_engine(request)
    workflow = _parse_workflow(body)

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


@router.post("/run/stream")
async def run_workflow_stream(body: WorkflowRunRequest, request: Request) -> StreamingResponse:
    """Start a new workflow run with real-time SSE streaming.

    Streams AgentEvents as Server-Sent Events. Each event has the format::

        event: {event_type}
        data: {"data": ..., "agent_name": ..., "timestamp": ...}

    Special events:
    - ``event: waiting_approval`` — workflow paused at a HITL gate
    - ``event: done`` — workflow completed, data contains run_id/status/result
    - ``event: error`` — an error occurred
    """
    engine = _get_engine(request)
    workflow = _parse_workflow(body)

    async def event_stream():
        run_id = None
        try:
            aiter = engine.run_workflow(
                workflow=workflow,
                input_data=body.input_data,
                session_id=body.session_id,
            )
            while True:
                try:
                    event = await asyncio.wait_for(
                        aiter.__anext__(), timeout=KEEPALIVE_INTERVAL
                    )
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    yield format_keepalive()
                    continue

                # Capture the run_id from the first event's engine state
                if run_id is None:
                    runs = engine.list_runs()
                    if runs:
                        run_id = runs[-1].run_id

                # Map HITL escalation events to a distinct SSE event type
                if (
                    event.type == AgentEventType.ESCALATION
                    and "gate" in event.data
                ):
                    yield format_sse("waiting_approval", {
                        "run_id": run_id,
                        **event.data,
                    })
                else:
                    yield format_sse(event.type.value, {
                        "data": event.data,
                        "agent_name": event.agent_name,
                        "timestamp": event.timestamp,
                    })

            # Terminal success event
            run = engine.get_run(run_id) if run_id else None
            yield format_sse("done", {
                "run_id": run.run_id if run else "unknown",
                "status": run.status.value if run else "failed",
                "result": run.result if run else None,
            })

        except Exception as exc:
            yield format_sse("error", {"error": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
