"""Tests for AI workflow generation endpoint."""

from __future__ import annotations

import pytest


class TestWorkflowGenerate:
    async def test_generate_returns_valid_structure(self, client):
        """Generation should return topology, agents, YAML, explanation."""
        resp = await client.post("/workflows/generate", json={
            "description": "Research AI trends, analyze the findings, write a blog post",
        })
        assert resp.status_code == 200
        data = resp.json()

        assert "topology" in data
        assert data["topology"] in ("sequential", "parallel", "graph", "hierarchical")
        assert "agents" in data
        assert len(data["agents"]) >= 2
        assert "workflow_yaml" in data
        assert "apiVersion" in data["workflow_yaml"]
        assert "explanation" in data
        assert len(data["explanation"]) > 10

    async def test_generate_research_pattern(self, client):
        """Research-type description should produce sequential topology."""
        resp = await client.post("/workflows/generate", json={
            "description": "Research quantum computing and summarize the key findings",
        })
        assert resp.status_code == 200
        data = resp.json()
        # Should be sequential (research → summarize)
        assert data["topology"] in ("sequential", "graph")
        assert len(data["agents"]) >= 2

    async def test_generate_triage_pattern(self, client):
        """Triage-type description should produce hierarchical topology."""
        resp = await client.post("/workflows/generate", json={
            "description": "Triage customer support tickets and route them to the right specialist",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["topology"] in ("hierarchical", "graph")

    async def test_generate_with_available_agents(self, client):
        """Available agents should influence the generated workflow."""
        resp = await client.post("/workflows/generate", json={
            "description": "Analyze market data",
            "available_agents": ["data-analyst", "report-writer"],
            "available_tools": ["web-search/search"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data

    async def test_generate_missing_description(self, client):
        """Missing description should return 400."""
        resp = await client.post("/workflows/generate", json={})
        assert resp.status_code == 400

    async def test_generate_empty_description(self, client):
        resp = await client.post("/workflows/generate", json={"description": ""})
        assert resp.status_code == 400

    async def test_generate_includes_suggested_input(self, client):
        resp = await client.post("/workflows/generate", json={
            "description": "Research and summarize a topic",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "suggested_input" in data

    async def test_generate_workflow_name(self, client):
        resp = await client.post("/workflows/generate", json={
            "description": "Research AI trends and summarize findings",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "workflow_name" in data
        assert len(data["workflow_name"]) > 0
