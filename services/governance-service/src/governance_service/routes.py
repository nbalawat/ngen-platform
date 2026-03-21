"""REST API routes for the governance service.

Provides CRUD for policies and a POST /evaluate endpoint that checks
an evaluation context against all applicable policies.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, Request

from governance_service.engine import PolicyEngine
from governance_service.models import (
    EvalContext,
    EvalResult,
    Policy,
    PolicyCreate,
    PolicyUpdate,
)
from governance_service.repository import PolicyRepository

router = APIRouter(prefix="/api/v1/policies", tags=["policies"])

# Module-level singletons — reset in tests via conftest
_repository: PolicyRepository | None = None
_engine: PolicyEngine | None = None


def _get_repository() -> PolicyRepository:
    global _repository
    if _repository is None:
        _repository = PolicyRepository()
    return _repository


def _get_engine() -> PolicyEngine:
    global _engine
    if _engine is None:
        _engine = PolicyEngine(_get_repository())
    return _engine


# ---------------------------------------------------------------------------
# Policy CRUD
# ---------------------------------------------------------------------------


@router.post("", status_code=201, response_model=Policy)
async def create_policy(body: PolicyCreate) -> Policy:
    repo = _get_repository()
    existing = repo.get_by_name(body.name, body.namespace)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Policy '{body.name}' already exists in namespace '{body.namespace}'",
        )
    return repo.create(body)


@router.get("", response_model=list[Policy])
async def list_policies(
    namespace: str | None = Query(default=None),
    policy_type: str | None = Query(default=None, alias="type"),
) -> list[Policy]:
    return _get_repository().list(namespace=namespace, policy_type=policy_type)


@router.get("/{policy_id}", response_model=Policy)
async def get_policy(policy_id: str) -> Policy:
    policy = _get_repository().get(policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


@router.get("/by-name/{name}", response_model=Policy)
async def get_policy_by_name(
    name: str,
    namespace: str = Query(default="default"),
) -> Policy:
    policy = _get_repository().get_by_name(name, namespace)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


@router.patch("/{policy_id}", response_model=Policy)
async def update_policy(policy_id: str, body: PolicyUpdate) -> Policy:
    policy = _get_repository().update(policy_id, body)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


@router.delete("/{policy_id}", status_code=204)
async def delete_policy(policy_id: str) -> None:
    if not _get_repository().delete(policy_id):
        raise HTTPException(status_code=404, detail="Policy not found")


# ---------------------------------------------------------------------------
# Policy evaluation
# ---------------------------------------------------------------------------

eval_router = APIRouter(prefix="/api/v1", tags=["evaluation"])


logger = logging.getLogger(__name__)


@eval_router.post("/evaluate", response_model=EvalResult)
async def evaluate(body: EvalContext, request: Request) -> EvalResult:
    result = _get_engine().evaluate(body)

    # Publish audit event (fire-and-forget)
    event_bus = getattr(request.app.state, "event_bus", None)
    if event_bus is not None:
        try:
            from ngen_common.events import Subjects, publish_audit_event
            asyncio.get_running_loop().create_task(
                publish_audit_event(
                    event_bus,
                    subject=Subjects.AUDIT_POLICY_EVALUATED,
                    data={
                        "namespace": body.namespace,
                        "agent_name": body.agent_name,
                        "allowed": result.allowed,
                        "violations": len(result.violations),
                        "warnings": len(result.warnings),
                        "evaluated_policies": result.evaluated_policies,
                    },
                    source="governance-service",
                )
            )
        except Exception:
            logger.debug("Failed to publish audit event", exc_info=True)

    return result
