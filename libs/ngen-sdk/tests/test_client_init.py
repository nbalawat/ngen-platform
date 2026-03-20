"""Tests for NgenClient initialization and lifecycle."""

from __future__ import annotations

import httpx
import pytest

from ngen_sdk import NgenClient


class TestClientInit:
    async def test_default_base_url(self):
        async with NgenClient() as client:
            assert client.workflows._base == "http://localhost:8080"
            assert client.models._base == "http://localhost:8080"

    async def test_custom_base_url(self):
        async with NgenClient(base_url="http://my-cluster:9000") as client:
            assert client.workflows._base == "http://my-cluster:9000"
            assert client.models._base == "http://my-cluster:9000"

    async def test_per_service_urls(self):
        async with NgenClient(
            workflow_url="http://wf:8003",
            registry_url="http://reg:8001",
            governance_url="http://gov:8004",
            mcp_url="http://mcp:8005",
            tenant_url="http://tenant:8000",
        ) as client:
            assert client.workflows._base == "http://wf:8003"
            assert client.models._base == "http://reg:8001"
            assert client.governance._base == "http://gov:8004"
            assert client.mcp._base == "http://mcp:8005"
            assert client.tenants._base == "http://tenant:8000"

    async def test_custom_http_client(self):
        http = httpx.AsyncClient()
        client = NgenClient(http_client=http)
        assert client._owns_http is False
        # Should not close the external client
        await client.close()
        assert not http.is_closed
        await http.aclose()

    async def test_context_manager(self):
        async with NgenClient() as client:
            assert client._owns_http is True
        # After exit, http should be closed
        assert client._http.is_closed

    async def test_has_all_sub_clients(self):
        async with NgenClient() as client:
            assert hasattr(client, "workflows")
            assert hasattr(client, "models")
            assert hasattr(client, "governance")
            assert hasattr(client, "mcp")
            assert hasattr(client, "tenants")
