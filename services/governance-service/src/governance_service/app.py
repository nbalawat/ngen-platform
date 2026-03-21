"""FastAPI application for the governance service."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI

from governance_service.budget_tracker import BudgetTracker
from governance_service.redis_repository import create_policy_repository
from governance_service.repository import PolicyRepository
from governance_service.routes import budget_router, eval_router, router
from ngen_common.auth import add_auth
from ngen_common.auth_config import make_auth_config
from ngen_common.cors import add_cors
from ngen_common.error_handlers import add_error_handlers
from ngen_common.events import add_event_bus
from ngen_common.observability import add_observability

logger = logging.getLogger(__name__)


def create_app(
    repository: PolicyRepository | None = None,
) -> FastAPI:
    application = FastAPI(
        title="NGEN Governance Service",
        version="0.1.0",
    )

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    application.include_router(router)
    application.include_router(eval_router)
    application.include_router(budget_router)
    add_error_handlers(application)
    add_cors(application)
    add_observability(application, service_name="governance-service")
    add_auth(application, make_auth_config())
    bus = add_event_bus(application, service_name="governance-service")

    # Budget tracker — subscribes to cost events for threshold enforcement
    repo = repository or create_policy_repository()
    tracker = BudgetTracker(event_bus=bus, repository=repo)
    application.state.budget_tracker = tracker

    @application.on_event("startup")
    async def _start_budget_tracker() -> None:
        await tracker.start()
        logger.info("BudgetTracker started")

    @application.on_event("shutdown")
    async def _stop_budget_tracker() -> None:
        await tracker.stop()
        logger.info("BudgetTracker stopped")

    return application


app = create_app()
