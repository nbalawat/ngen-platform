"""Onboarding Agent — guides new tenants through platform setup.

The onboarding agent is the first real AI agent on the NGEN platform.
It helps new tenants:
1. Create their organization, teams, and projects
2. Register models they want to use
3. Set up governance policies
4. Register MCP tool servers
5. Run their first workflow

The agent uses the NgenClient SDK to interact with platform services
and provides a conversational interface via REST API.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from ngen_common.auth import add_auth
from ngen_common.auth_config import make_auth_config
from ngen_common.cors import add_cors
from ngen_common.error_handlers import add_error_handlers
from ngen_common.observability import add_observability

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class OnboardingRequest(BaseModel):
    """Request to the onboarding agent."""

    message: str
    tenant_id: str = "default"
    session_id: str | None = None


class OnboardingResponse(BaseModel):
    """Response from the onboarding agent."""

    message: str
    actions_taken: list[dict] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    session_id: str | None = None


class PlatformStatus(BaseModel):
    """Current status of a tenant's platform setup."""

    tenant_id: str
    has_organization: bool = False
    model_count: int = 0
    policy_count: int = 0
    server_count: int = 0
    workflow_run_count: int = 0


# ---------------------------------------------------------------------------
# Onboarding logic
# ---------------------------------------------------------------------------


ONBOARDING_STEPS = [
    "Create an organization for your team",
    "Register AI models (Anthropic, OpenAI, or local Ollama)",
    "Set up governance policies (content filters, cost limits)",
    "Register MCP tool servers for agent capabilities",
    "Run your first multi-agent workflow",
]


async def _check_platform_status(tenant_id: str) -> PlatformStatus:
    """Check what the tenant has already set up."""
    import httpx

    status = PlatformStatus(tenant_id=tenant_id)

    base_urls = {
        "tenant": os.environ.get("TENANT_SERVICE_URL", "http://localhost:8000"),
        "registry": os.environ.get("MODEL_REGISTRY_URL", "http://localhost:8001"),
        "governance": os.environ.get("GOVERNANCE_URL", "http://localhost:8004"),
        "mcp": os.environ.get("MCP_MANAGER_URL", "http://localhost:8005"),
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(f"{base_urls['tenant']}/api/v1/orgs")
            if resp.status_code == 200:
                orgs = resp.json()
                status.has_organization = len(orgs) > 0
        except Exception:
            pass

        try:
            resp = await client.get(f"{base_urls['registry']}/api/v1/models")
            if resp.status_code == 200:
                status.model_count = len(resp.json())
        except Exception:
            pass

        try:
            resp = await client.get(f"{base_urls['governance']}/api/v1/policies")
            if resp.status_code == 200:
                status.policy_count = len(resp.json())
        except Exception:
            pass

        try:
            resp = await client.get(f"{base_urls['mcp']}/api/v1/servers")
            if resp.status_code == 200:
                status.server_count = len(resp.json())
        except Exception:
            pass

    return status


def _generate_response(message: str, status: PlatformStatus) -> OnboardingResponse:
    """Generate an onboarding response based on platform status."""
    actions_taken = []
    next_steps = []

    # Determine what's missing
    if not status.has_organization:
        next_steps.append("Create your organization: POST /api/v1/orgs")
    if status.model_count == 0:
        next_steps.append("Register a model: POST /api/v1/models")
    if status.policy_count == 0:
        next_steps.append("Create a governance policy: POST /api/v1/policies")
    if status.server_count == 0:
        next_steps.append("Register an MCP server: POST /api/v1/servers")

    if not next_steps:
        next_steps.append("Run a workflow: POST /workflows/run")
        response_msg = (
            f"Your platform is fully set up! You have {status.model_count} models, "
            f"{status.policy_count} policies, and {status.server_count} MCP servers. "
            f"You're ready to run multi-agent workflows."
        )
    else:
        completed = 5 - len(next_steps)
        response_msg = (
            f"Welcome to NGEN! You've completed {completed}/5 onboarding steps. "
            f"Here's what to do next."
        )

    return OnboardingResponse(
        message=response_msg,
        actions_taken=actions_taken,
        next_steps=next_steps,
    )


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    application = FastAPI(
        title="NGEN Onboarding Agent",
        version="0.1.0",
        description="Guides new tenants through platform setup",
    )

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @application.post("/api/v1/onboard", response_model=OnboardingResponse)
    async def onboard(body: OnboardingRequest) -> OnboardingResponse:
        """Interact with the onboarding agent."""
        status = await _check_platform_status(body.tenant_id)
        return _generate_response(body.message, status)

    @application.get("/api/v1/onboard/status", response_model=PlatformStatus)
    async def get_status(tenant_id: str = "default") -> PlatformStatus:
        """Check current platform setup status."""
        return await _check_platform_status(tenant_id)

    @application.get("/api/v1/onboard/steps")
    async def get_steps() -> dict:
        """Get the onboarding checklist."""
        return {"steps": ONBOARDING_STEPS}

    add_error_handlers(application)
    add_cors(application)
    add_observability(application, service_name="onboarding-agent")
    add_auth(application, make_auth_config())
    return application


app = create_app()
