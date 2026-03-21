"""Load tests for the NGEN Platform.

Uses Locust for distributed load testing against the platform services.
Run with: locust -f tests/load/locustfile.py --host http://localhost

Services tested:
- Model Gateway (port 8002): chat completions
- Workflow Engine (port 8003): workflow runs + agent invocations
- Governance Service (port 8004): policy evaluation
- Model Registry (port 8001): model CRUD
- MCP Manager (port 8005): server + tool catalog
- Tenant Service (port 8000): org CRUD
"""

from __future__ import annotations

import json
import uuid

from locust import HttpUser, between, task


class ModelGatewayUser(HttpUser):
    """Simulates LLM API consumers hitting the model gateway."""

    host = "http://localhost:8002"
    wait_time = between(0.5, 2.0)

    @task(10)
    def chat_completion(self):
        self.client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [{"role": "user", "content": f"Load test {uuid.uuid4().hex[:8]}"}],
            },
            headers={"x-tenant-id": f"load-test-{uuid.uuid4().hex[:4]}"},
            name="/v1/chat/completions",
        )

    @task(2)
    def list_models(self):
        self.client.get("/v1/models", name="/v1/models")

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")


class WorkflowEngineUser(HttpUser):
    """Simulates workflow execution requests."""

    host = "http://localhost:8003"
    wait_time = between(1.0, 3.0)

    def _workflow_yaml(self, name: str) -> str:
        return (
            f"apiVersion: ngen.io/v1\n"
            f"kind: Workflow\n"
            f"metadata:\n"
            f"  name: {name}\n"
            f"spec:\n"
            f"  topology: sequential\n"
            f"  agents:\n"
            f"  - ref: load-agent\n"
        )

    @task(5)
    def run_workflow(self):
        name = f"load-wf-{uuid.uuid4().hex[:8]}"
        self.client.post(
            "/workflows/run",
            json={
                "workflow_yaml": self._workflow_yaml(name),
                "input_data": {"query": "load test"},
            },
            name="/workflows/run",
        )

    @task(3)
    def list_runs(self):
        self.client.get("/workflows/runs", name="/workflows/runs")

    @task(2)
    def create_and_invoke_agent(self):
        name = f"load-agent-{uuid.uuid4().hex[:8]}"
        self.client.post(
            "/agents",
            json={"name": name, "framework": "default"},
            name="/agents [create]",
        )
        self.client.post(
            f"/agents/{name}/invoke",
            json={"messages": [{"role": "user", "content": "hello"}]},
            name="/agents/{name}/invoke",
        )
        self.client.delete(f"/agents/{name}", name="/agents/{name} [delete]")

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")


class GovernanceUser(HttpUser):
    """Simulates policy evaluation requests."""

    host = "http://localhost:8004"
    wait_time = between(0.5, 1.5)

    @task(10)
    def evaluate(self):
        self.client.post(
            "/api/v1/evaluate",
            json={
                "namespace": "default",
                "content": f"Load test content {uuid.uuid4().hex}",
                "agent_name": "load-agent",
            },
            name="/api/v1/evaluate",
        )

    @task(3)
    def list_policies(self):
        self.client.get("/api/v1/policies", name="/api/v1/policies")

    @task(2)
    def get_budget(self):
        self.client.get("/api/v1/budgets/default", name="/api/v1/budgets/{ns}")

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")


class TenantServiceUser(HttpUser):
    """Simulates tenant management operations."""

    host = "http://localhost:8000"
    wait_time = between(1.0, 3.0)

    @task(5)
    def list_orgs(self):
        self.client.get("/api/v1/orgs", name="/api/v1/orgs")

    @task(2)
    def create_and_delete_org(self):
        suffix = uuid.uuid4().hex[:8]
        resp = self.client.post(
            "/api/v1/orgs",
            json={
                "name": f"load-org-{suffix}",
                "slug": f"load-org-{suffix}",
                "contact_email": f"load-{suffix}@test.com",
            },
            name="/api/v1/orgs [create]",
        )
        if resp.status_code == 201:
            org_id = resp.json().get("id")
            if org_id:
                self.client.delete(
                    f"/api/v1/orgs/{org_id}",
                    name="/api/v1/orgs/{id} [delete]",
                )

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")


class MCPManagerUser(HttpUser):
    """Simulates MCP tool catalog browsing."""

    host = "http://localhost:8005"
    wait_time = between(1.0, 2.0)

    @task(5)
    def list_servers(self):
        self.client.get("/api/v1/servers", name="/api/v1/servers")

    @task(3)
    def list_tools(self):
        self.client.get("/api/v1/tools", name="/api/v1/tools")

    @task(2)
    def search_tools(self):
        self.client.get(
            "/api/v1/tools/search?q=search",
            name="/api/v1/tools/search",
        )

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")
