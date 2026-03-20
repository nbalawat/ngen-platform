"""NGEN Platform SDK client.

Provides a unified async Python client for all NGEN platform services:
- Workflow Engine: run workflows, stream execution, manage runs
- Model Registry: register, list, manage AI models
- Governance: create and evaluate policies
- MCP Manager: register servers, discover tools, invoke tools
- Tenant Service: manage orgs, teams, projects

Usage:
    from ngen_sdk import NgenClient

    async with NgenClient(base_url="http://localhost:8080") as client:
        result = await client.workflows.run(spec, input_data={"query": "hello"})
        models = await client.models.list()
"""

from __future__ import annotations

import json
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Sub-clients for each service
# ---------------------------------------------------------------------------


class WorkflowClient:
    """Client for the Workflow Engine service."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base = base_url

    async def run(
        self,
        spec: dict[str, Any],
        *,
        input_data: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Submit a workflow for blocking execution."""
        body: dict[str, Any] = {"spec": spec}
        if input_data:
            body["input"] = input_data
        if session_id:
            body["session_id"] = session_id
        resp = await self._http.post(f"{self._base}/workflows/run", json=body)
        resp.raise_for_status()
        return resp.json()

    async def stream(
        self,
        spec: dict[str, Any],
        *,
        input_data: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Submit a workflow for SSE streaming and collect all events."""
        body: dict[str, Any] = {"spec": spec}
        if input_data:
            body["input"] = input_data
        if session_id:
            body["session_id"] = session_id

        events: list[dict[str, Any]] = []
        async with self._http.stream(
            "POST", f"{self._base}/workflows/stream", json=body
        ) as resp:
            resp.raise_for_status()
            current_event: str | None = None
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("event: "):
                    current_event = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                    events.append({
                        "event": current_event or "message",
                        "data": data,
                    })
                    current_event = None
        return events

    async def list_runs(self) -> list[dict[str, Any]]:
        resp = await self._http.get(f"{self._base}/workflows/runs")
        resp.raise_for_status()
        return resp.json()

    async def get_run(self, run_id: str) -> dict[str, Any]:
        resp = await self._http.get(f"{self._base}/workflows/runs/{run_id}")
        resp.raise_for_status()
        return resp.json()

    async def approve(self, run_id: str) -> dict[str, Any]:
        resp = await self._http.post(
            f"{self._base}/workflows/runs/{run_id}/approve"
        )
        resp.raise_for_status()
        return resp.json()

    async def cancel(self, run_id: str) -> dict[str, Any]:
        resp = await self._http.post(
            f"{self._base}/workflows/runs/{run_id}/cancel"
        )
        resp.raise_for_status()
        return resp.json()


class ModelClient:
    """Client for the Model Registry service."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base = base_url

    async def list(self, provider: str | None = None) -> list[dict[str, Any]]:
        params = {}
        if provider:
            params["provider"] = provider
        resp = await self._http.get(
            f"{self._base}/api/v1/models", params=params
        )
        resp.raise_for_status()
        return resp.json()

    async def get(self, model_id: str) -> dict[str, Any]:
        resp = await self._http.get(f"{self._base}/api/v1/models/{model_id}")
        resp.raise_for_status()
        return resp.json()

    async def register(self, model: dict[str, Any]) -> dict[str, Any]:
        resp = await self._http.post(f"{self._base}/api/v1/models", json=model)
        resp.raise_for_status()
        return resp.json()

    async def delete(self, model_id: str) -> None:
        resp = await self._http.delete(f"{self._base}/api/v1/models/{model_id}")
        resp.raise_for_status()


class GovernanceClient:
    """Client for the Governance service."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base = base_url

    async def create_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        resp = await self._http.post(
            f"{self._base}/api/v1/policies", json=policy
        )
        resp.raise_for_status()
        return resp.json()

    async def list_policies(
        self, namespace: str | None = None
    ) -> list[dict[str, Any]]:
        params = {}
        if namespace:
            params["namespace"] = namespace
        resp = await self._http.get(
            f"{self._base}/api/v1/policies", params=params
        )
        resp.raise_for_status()
        return resp.json()

    async def get_policy(self, policy_id: str) -> dict[str, Any]:
        resp = await self._http.get(
            f"{self._base}/api/v1/policies/{policy_id}"
        )
        resp.raise_for_status()
        return resp.json()

    async def update_policy(
        self, policy_id: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        resp = await self._http.patch(
            f"{self._base}/api/v1/policies/{policy_id}", json=updates
        )
        resp.raise_for_status()
        return resp.json()

    async def delete_policy(self, policy_id: str) -> None:
        resp = await self._http.delete(
            f"{self._base}/api/v1/policies/{policy_id}"
        )
        resp.raise_for_status()

    async def evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
        resp = await self._http.post(
            f"{self._base}/api/v1/evaluate", json=context
        )
        resp.raise_for_status()
        return resp.json()


class MCPClient:
    """Client for the MCP Manager service."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base = base_url

    async def register_server(
        self, server: dict[str, Any]
    ) -> dict[str, Any]:
        resp = await self._http.post(
            f"{self._base}/api/v1/servers", json=server
        )
        resp.raise_for_status()
        return resp.json()

    async def list_servers(
        self, namespace: str | None = None
    ) -> list[dict[str, Any]]:
        params = {}
        if namespace:
            params["namespace"] = namespace
        resp = await self._http.get(
            f"{self._base}/api/v1/servers", params=params
        )
        resp.raise_for_status()
        return resp.json()

    async def get_server(self, server_id: str) -> dict[str, Any]:
        resp = await self._http.get(
            f"{self._base}/api/v1/servers/{server_id}"
        )
        resp.raise_for_status()
        return resp.json()

    async def delete_server(self, server_id: str) -> None:
        resp = await self._http.delete(
            f"{self._base}/api/v1/servers/{server_id}"
        )
        resp.raise_for_status()

    async def list_tools(
        self,
        server_name: str | None = None,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        params = {}
        if server_name:
            params["server_name"] = server_name
        if tag:
            params["tag"] = tag
        resp = await self._http.get(
            f"{self._base}/api/v1/tools", params=params
        )
        resp.raise_for_status()
        return resp.json()

    async def search_tools(self, query: str) -> list[dict[str, Any]]:
        resp = await self._http.get(
            f"{self._base}/api/v1/tools/search", params={"q": query}
        )
        resp.raise_for_status()
        return resp.json()

    async def invoke(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        namespace: str = "default",
    ) -> dict[str, Any]:
        resp = await self._http.post(
            f"{self._base}/api/v1/invoke",
            json={
                "server_name": server_name,
                "tool_name": tool_name,
                "arguments": arguments or {},
                "namespace": namespace,
            },
        )
        resp.raise_for_status()
        return resp.json()


class TenantClient:
    """Client for the Tenant service."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base = base_url

    async def create_org(self, org: dict[str, Any]) -> dict[str, Any]:
        resp = await self._http.post(f"{self._base}/orgs", json=org)
        resp.raise_for_status()
        return resp.json()

    async def list_orgs(self) -> list[dict[str, Any]]:
        resp = await self._http.get(f"{self._base}/orgs")
        resp.raise_for_status()
        return resp.json()

    async def get_org(self, org_id: str) -> dict[str, Any]:
        resp = await self._http.get(f"{self._base}/orgs/{org_id}")
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------


class NgenClient:
    """Unified NGEN Platform SDK client.

    Can be used as an async context manager or manually opened/closed.

    Args:
        base_url: Base URL for the NGEN platform gateway (default: http://localhost:8080)
        workflow_url: Override URL for the workflow engine
        registry_url: Override URL for the model registry
        governance_url: Override URL for the governance service
        mcp_url: Override URL for the MCP manager
        tenant_url: Override URL for the tenant service
        timeout: Request timeout in seconds (default: 30)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        *,
        workflow_url: str | None = None,
        registry_url: str | None = None,
        governance_url: str | None = None,
        mcp_url: str | None = None,
        tenant_url: str | None = None,
        timeout: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout)
        )
        self._owns_http = http_client is None

        self.workflows = WorkflowClient(
            self._http, workflow_url or base_url
        )
        self.models = ModelClient(self._http, registry_url or base_url)
        self.governance = GovernanceClient(
            self._http, governance_url or base_url
        )
        self.mcp = MCPClient(self._http, mcp_url or base_url)
        self.tenants = TenantClient(self._http, tenant_url or base_url)

    async def health(self, service_url: str | None = None) -> dict[str, str]:
        """Check health of a service."""
        url = service_url or f"{self.workflows._base}/health"
        resp = await self._http.get(url)
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> NgenClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
