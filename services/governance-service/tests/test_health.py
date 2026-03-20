"""Tests for governance service health endpoint."""

from __future__ import annotations


class TestHealth:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
