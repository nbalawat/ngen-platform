from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


async def test_health_check(client: httpx.AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"


# ---------------------------------------------------------------------------
# Organizations CRUD
# ---------------------------------------------------------------------------


class TestOrganizationEndpoints:
    async def test_create_org(
        self,
        client: httpx.AsyncClient,
        sample_org_payload: dict[str, Any],
    ):
        resp = await client.post(
            "/api/v1/orgs", json=sample_org_payload
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert "created_at" in body
        assert body["name"] == sample_org_payload["name"]
        assert body["slug"] == sample_org_payload["slug"]

    async def test_create_org_duplicate_slug(
        self,
        client: httpx.AsyncClient,
        sample_org_payload: dict[str, Any],
    ):
        resp1 = await client.post(
            "/api/v1/orgs", json=sample_org_payload
        )
        assert resp1.status_code == 201

        resp2 = await client.post(
            "/api/v1/orgs", json=sample_org_payload
        )
        assert resp2.status_code == 409

    async def test_list_orgs(
        self,
        client: httpx.AsyncClient,
        sample_org_payload: dict[str, Any],
    ):
        await client.post(
            "/api/v1/orgs", json=sample_org_payload
        )
        resp = await client.get("/api/v1/orgs")
        assert resp.status_code == 200
        items = resp.json()
        assert isinstance(items, list)
        assert len(items) >= 1

    async def test_get_org_by_id(
        self,
        client: httpx.AsyncClient,
        sample_org_payload: dict[str, Any],
    ):
        create_resp = await client.post(
            "/api/v1/orgs", json=sample_org_payload
        )
        org_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/orgs/{org_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == org_id

    async def test_get_org_not_found(
        self, client: httpx.AsyncClient
    ):
        fake_id = str(uuid4())
        resp = await client.get(f"/api/v1/orgs/{fake_id}")
        assert resp.status_code == 404

    async def test_update_org(
        self,
        client: httpx.AsyncClient,
        sample_org_payload: dict[str, Any],
    ):
        create_resp = await client.post(
            "/api/v1/orgs", json=sample_org_payload
        )
        org_id = create_resp.json()["id"]

        patch_resp = await client.patch(
            f"/api/v1/orgs/{org_id}",
            json={"name": "Acme Renamed"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["name"] == "Acme Renamed"

    async def test_delete_org(
        self,
        client: httpx.AsyncClient,
        sample_org_payload: dict[str, Any],
    ):
        create_resp = await client.post(
            "/api/v1/orgs", json=sample_org_payload
        )
        org_id = create_resp.json()["id"]

        del_resp = await client.delete(
            f"/api/v1/orgs/{org_id}"
        )
        assert del_resp.status_code == 204

        get_resp = await client.get(
            f"/api/v1/orgs/{org_id}"
        )
        assert get_resp.status_code == 404

    async def test_delete_org_not_found(
        self, client: httpx.AsyncClient
    ):
        fake_id = str(uuid4())
        resp = await client.delete(
            f"/api/v1/orgs/{fake_id}"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Helper: create an org and return its id
# ---------------------------------------------------------------------------


async def _create_org(
    client: httpx.AsyncClient,
    slug: str = "test-org",
) -> str:
    payload = {
        "name": "Test Organization",
        "slug": slug,
        "contact_email": "test@org.com",
    }
    resp = await client.post("/api/v1/orgs", json=payload)
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Teams (scoped to org)
# ---------------------------------------------------------------------------


class TestTeamEndpoints:
    async def test_create_team(
        self,
        client: httpx.AsyncClient,
        sample_team_payload: dict[str, Any],
    ):
        org_id = await _create_org(client)
        resp = await client.post(
            f"/api/v1/orgs/{org_id}/teams",
            json=sample_team_payload,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["name"] == sample_team_payload["name"]

    async def test_list_teams(
        self,
        client: httpx.AsyncClient,
        sample_team_payload: dict[str, Any],
    ):
        org_id = await _create_org(client)
        await client.post(
            f"/api/v1/orgs/{org_id}/teams",
            json=sample_team_payload,
        )

        resp = await client.get(
            f"/api/v1/orgs/{org_id}/teams"
        )
        assert resp.status_code == 200
        items = resp.json()
        assert isinstance(items, list)
        assert len(items) == 1

    async def test_get_team_by_id(
        self,
        client: httpx.AsyncClient,
        sample_team_payload: dict[str, Any],
    ):
        org_id = await _create_org(client)
        create_resp = await client.post(
            f"/api/v1/orgs/{org_id}/teams",
            json=sample_team_payload,
        )
        team_id = create_resp.json()["id"]

        resp = await client.get(
            f"/api/v1/orgs/{org_id}/teams/{team_id}"
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == team_id

    async def test_delete_team(
        self,
        client: httpx.AsyncClient,
        sample_team_payload: dict[str, Any],
    ):
        org_id = await _create_org(client)
        create_resp = await client.post(
            f"/api/v1/orgs/{org_id}/teams",
            json=sample_team_payload,
        )
        team_id = create_resp.json()["id"]

        del_resp = await client.delete(
            f"/api/v1/orgs/{org_id}/teams/{team_id}"
        )
        assert del_resp.status_code == 204


# ---------------------------------------------------------------------------
# Projects (scoped to team)
# ---------------------------------------------------------------------------


async def _create_team(
    client: httpx.AsyncClient, org_id: str,
    slug: str = "test-team",
) -> str:
    payload = {"name": "Test Team", "slug": slug}
    resp = await client.post(
        f"/api/v1/orgs/{org_id}/teams", json=payload
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestProjectEndpoints:
    async def test_create_project(
        self,
        client: httpx.AsyncClient,
        sample_project_payload: dict[str, Any],
    ):
        org_id = await _create_org(client)
        team_id = await _create_team(client, org_id)
        resp = await client.post(
            f"/api/v1/orgs/{org_id}/teams/{team_id}/projects",
            json=sample_project_payload,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["name"] == sample_project_payload["name"]

    async def test_list_projects(
        self,
        client: httpx.AsyncClient,
        sample_project_payload: dict[str, Any],
    ):
        org_id = await _create_org(client)
        team_id = await _create_team(client, org_id)
        await client.post(
            f"/api/v1/orgs/{org_id}/teams/{team_id}/projects",
            json=sample_project_payload,
        )

        resp = await client.get(
            f"/api/v1/orgs/{org_id}/teams/{team_id}/projects"
        )
        assert resp.status_code == 200
        items = resp.json()
        assert isinstance(items, list)
        assert len(items) == 1

    async def test_delete_project(
        self,
        client: httpx.AsyncClient,
        sample_project_payload: dict[str, Any],
    ):
        org_id = await _create_org(client)
        team_id = await _create_team(client, org_id)
        create_resp = await client.post(
            f"/api/v1/orgs/{org_id}/teams/{team_id}/projects",
            json=sample_project_payload,
        )
        proj_id = create_resp.json()["id"]

        del_resp = await client.delete(
            f"/api/v1/orgs/{org_id}/teams/{team_id}"
            f"/projects/{proj_id}"
        )
        assert del_resp.status_code == 204


# ---------------------------------------------------------------------------
# Data isolation
# ---------------------------------------------------------------------------


class TestDataIsolation:
    async def test_teams_scoped_to_org(
        self, client: httpx.AsyncClient
    ):
        """Teams from org A must not appear in org B listings."""
        org_a = await _create_org(client, slug="org-alpha")
        org_b = await _create_org(client, slug="org-beta")

        await client.post(
            f"/api/v1/orgs/{org_a}/teams",
            json={
                "name": "Alpha Team",
                "slug": "alpha-team",
            },
        )

        resp_b = await client.get(
            f"/api/v1/orgs/{org_b}/teams"
        )
        assert resp_b.status_code == 200
        assert resp_b.json() == []

        resp_a = await client.get(
            f"/api/v1/orgs/{org_a}/teams"
        )
        assert resp_a.status_code == 200
        assert len(resp_a.json()) == 1
