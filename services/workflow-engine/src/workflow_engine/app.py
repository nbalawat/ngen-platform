"""Workflow Engine FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from ngen_framework_core.executor import AgentExecutor
from ngen_framework_core.registry import AdapterRegistry

from ngen_common.auth import add_auth
from ngen_common.auth_config import make_auth_config
from ngen_common.cors import add_cors
from ngen_common.error_handlers import add_error_handlers
from ngen_common.events import add_event_bus
from ngen_common.observability import add_observability
from workflow_engine.agent_manager import AgentRegistry, agent_router
from workflow_engine.config import Settings
from workflow_engine.default_adapter import DefaultAdapter
from workflow_engine.engine import WorkflowEngine
from workflow_engine.governance import GovernanceGuard
from workflow_engine.routes import router
from workflow_engine.version_routes import version_router
from workflow_engine.version_store import VersionStore

logger = logging.getLogger(__name__)


def create_app(
    executor: AgentExecutor | None = None,
    settings: Settings | None = None,
    default_framework: str = "default",
    governance_guard: GovernanceGuard | None = None,
) -> FastAPI:
    """Create and configure the Workflow Engine FastAPI application.

    Args:
        executor: AgentExecutor instance. Creates a default one if not provided.
        settings: Application settings. Loads from env if not provided.
        default_framework: Framework name for agent creation.
        governance_guard: Optional GovernanceGuard for policy enforcement.
    """
    _settings = settings or Settings()
    if executor is None:
        # Register the built-in default adapter so agents can always be created
        registry = AdapterRegistry()
        registry.register(DefaultAdapter())
        _executor = AgentExecutor(registry=registry)
    else:
        _executor = executor

    app = FastAPI(
        title="NGEN Workflow Engine",
        version="0.1.0",
        description="Multi-agent workflow orchestration service",
    )

    # Dependency injection via app.state
    app.state.settings = _settings
    app.state.executor = _executor
    app.state.engine = WorkflowEngine(
        executor=_executor,
        max_concurrent=_settings.MAX_CONCURRENT_RUNS,
        human_approval_timeout=_settings.HUMAN_APPROVAL_TIMEOUT,
        default_framework=default_framework,
        governance_guard=governance_guard,
    )

    app.state.agent_registry = AgentRegistry()
    app.state.version_store = VersionStore()
    app.include_router(router)
    app.include_router(agent_router)
    app.include_router(version_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    add_error_handlers(app)
    add_observability(app, service_name="workflow-engine")
    add_auth(app, make_auth_config())
    add_event_bus(app, service_name="workflow-engine")
    return app
