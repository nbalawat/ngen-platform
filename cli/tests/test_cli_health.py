"""Tests for CLI health command against real in-process services."""

from __future__ import annotations


class TestHealth:
    async def test_workflow_engine_health(self, workflow_client):
        """Workflow engine health endpoint returns ok."""
        resp = await workflow_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_registry_health(self, registry_client):
        """Model registry health endpoint returns healthy."""
        resp = await registry_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
