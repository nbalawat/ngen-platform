"""HTTP client for communicating with NGEN platform services."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx


class NgenClient:
    """Async HTTP client for NGEN platform services.

    Provides methods to call the Workflow Engine, Model Registry,
    and other platform services via their REST APIs.
    """

    def __init__(
        self,
        workflow_url: str = "http://localhost:8003",
        registry_url: str = "http://localhost:8002",
        gateway_url: str = "http://localhost:8001",
        timeout: float = 300.0,
    ) -> None:
        self.workflow_url = workflow_url.rstrip("/")
        self.registry_url = registry_url.rstrip("/")
        self.gateway_url = gateway_url.rstrip("/")
        self.timeout = timeout

    # -- Workflow Engine -----------------------------------------------------

    async def run_workflow(
        self,
        workflow_yaml: str,
        input_data: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a workflow (blocking mode)."""
        payload: dict[str, Any] = {"workflow_yaml": workflow_yaml}
        if input_data:
            payload["input_data"] = input_data
        if session_id:
            payload["session_id"] = session_id

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.workflow_url}/workflows/run", json=payload
            )
            resp.raise_for_status()
            return resp.json()

    async def stream_workflow(
        self,
        workflow_yaml: str,
        input_data: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> AsyncIterator[str]:
        """Run a workflow with SSE streaming. Yields raw SSE lines."""
        payload: dict[str, Any] = {"workflow_yaml": workflow_yaml}
        if input_data:
            payload["input_data"] = input_data
        if session_id:
            payload["session_id"] = session_id

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.workflow_url}/workflows/run/stream",
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    yield line

    async def list_runs(
        self, status: str | None = None
    ) -> list[dict[str, Any]]:
        """List workflow runs."""
        params = {}
        if status:
            params["status"] = status
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.workflow_url}/workflows/runs", params=params
            )
            resp.raise_for_status()
            return resp.json()

    async def get_run(self, run_id: str) -> dict[str, Any]:
        """Get a specific workflow run."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.workflow_url}/workflows/runs/{run_id}"
            )
            resp.raise_for_status()
            return resp.json()

    async def approve_run(self, run_id: str) -> dict[str, Any]:
        """Approve a workflow run waiting at an HITL gate."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.workflow_url}/workflows/runs/{run_id}/approve"
            )
            resp.raise_for_status()
            return resp.json()

    async def cancel_run(self, run_id: str) -> dict[str, Any]:
        """Cancel a running workflow."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.delete(
                f"{self.workflow_url}/workflows/runs/{run_id}"
            )
            resp.raise_for_status()
            return resp.json()

    # -- Model Registry ------------------------------------------------------

    async def list_models(
        self, provider: str | None = None
    ) -> list[dict[str, Any]]:
        """List registered models."""
        params = {}
        if provider:
            params["provider"] = provider
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.registry_url}/api/v1/models", params=params
            )
            resp.raise_for_status()
            return resp.json()

    async def get_model(self, model_id: str) -> dict[str, Any]:
        """Get a model by ID or name."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Try by name first, fall back to UUID
            resp = await client.get(
                f"{self.registry_url}/api/v1/models/by-name/{model_id}"
            )
            if resp.status_code == 404:
                resp = await client.get(
                    f"{self.registry_url}/api/v1/models/{model_id}"
                )
            resp.raise_for_status()
            return resp.json()

    async def register_model(self, data: dict[str, Any]) -> dict[str, Any]:
        """Register a new model."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.registry_url}/api/v1/models", json=data
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_model(self, model_id: str) -> None:
        """Delete a model by UUID."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.delete(
                f"{self.registry_url}/api/v1/models/{model_id}"
            )
            resp.raise_for_status()

    # -- Health ---------------------------------------------------------------

    async def check_health(self, service_url: str) -> dict[str, Any]:
        """Check a service's health endpoint."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{service_url}/health")
            resp.raise_for_status()
            return resp.json()
