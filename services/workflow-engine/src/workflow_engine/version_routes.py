"""REST API routes for workflow and agent versioning."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from workflow_engine.version_store import VersionStore


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SaveWorkflowVersionRequest(BaseModel):
    name: str = Field(..., min_length=1)
    yaml_content: str = Field(..., min_length=1)
    input_data: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class SaveAgentVersionRequest(BaseModel):
    name: str = Field(..., min_length=1)
    system_prompt: str = ""
    framework: str = "default"
    model: str = "default"
    description: str = ""
    tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

version_router = APIRouter(prefix="/versions", tags=["versions"])


def _get_store(request: Request) -> VersionStore:
    return request.app.state.version_store


# Workflow versions

@version_router.post("/workflows", status_code=201)
async def save_workflow_version(body: SaveWorkflowVersionRequest, request: Request) -> dict:
    store = _get_store(request)
    v = store.save_workflow(
        name=body.name,
        yaml_content=body.yaml_content,
        input_data=body.input_data,
        description=body.description,
        metadata=body.metadata,
    )
    return {
        "workflow_name": v.workflow_name,
        "version": v.version,
        "description": v.description,
        "created_at": v.created_at,
    }


@version_router.get("/workflows")
async def list_saved_workflows(request: Request) -> list[dict]:
    return _get_store(request).list_workflows()


@version_router.get("/workflows/{name}")
async def list_workflow_versions(name: str, request: Request) -> list[dict]:
    store = _get_store(request)
    versions = store.list_workflow_versions(name)
    if not versions:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
    return [
        {
            "workflow_name": v.workflow_name,
            "version": v.version,
            "description": v.description,
            "created_at": v.created_at,
            "yaml_length": len(v.yaml_content),
        }
        for v in versions
    ]


@version_router.get("/workflows/{name}/{version}")
async def get_workflow_version(name: str, version: int, request: Request) -> dict:
    store = _get_store(request)
    v = store.get_workflow_version(name, version)
    if v is None:
        raise HTTPException(status_code=404, detail=f"Version {version} not found for '{name}'")
    return {
        "workflow_name": v.workflow_name,
        "version": v.version,
        "yaml_content": v.yaml_content,
        "input_data": v.input_data,
        "description": v.description,
        "created_at": v.created_at,
        "metadata": v.metadata,
    }


# Agent versions

@version_router.post("/agents", status_code=201)
async def save_agent_version(body: SaveAgentVersionRequest, request: Request) -> dict:
    store = _get_store(request)
    v = store.save_agent(
        name=body.name,
        system_prompt=body.system_prompt,
        framework=body.framework,
        model=body.model,
        description=body.description,
        tools=body.tools,
        metadata=body.metadata,
    )
    return {
        "agent_name": v.agent_name,
        "version": v.version,
        "description": v.description,
        "created_at": v.created_at,
    }


@version_router.get("/agents")
async def list_saved_agents(request: Request) -> list[dict]:
    return _get_store(request).list_agents()


@version_router.get("/agents/{name}")
async def list_agent_versions(name: str, request: Request) -> list[dict]:
    store = _get_store(request)
    versions = store.list_agent_versions(name)
    if not versions:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return [
        {
            "agent_name": v.agent_name,
            "version": v.version,
            "description": v.description,
            "system_prompt_length": len(v.system_prompt),
            "framework": v.framework,
            "model": v.model,
            "created_at": v.created_at,
        }
        for v in versions
    ]


@version_router.get("/agents/{name}/{version}")
async def get_agent_version(name: str, version: int, request: Request) -> dict:
    store = _get_store(request)
    v = store.get_agent_version(name, version)
    if v is None:
        raise HTTPException(status_code=404, detail=f"Version {version} not found for '{name}'")
    return {
        "agent_name": v.agent_name,
        "version": v.version,
        "system_prompt": v.system_prompt,
        "framework": v.framework,
        "model": v.model,
        "description": v.description,
        "tools": v.tools,
        "created_at": v.created_at,
        "metadata": v.metadata,
    }
