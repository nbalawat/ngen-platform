"""Integration tests: tenant service CRUD against real PostgreSQL.

Exercises the full tenant service → PostgreSQL path with real data.
"""

from __future__ import annotations

import uuid

import httpx
import pytest


class TestTenantOrganizationCRUD:
    """Full CRUD lifecycle for organizations."""

    async def test_create_organization(self, http: httpx.AsyncClient, tenant_url):
        suffix = uuid.uuid4().hex[:8]
        resp = await http.post(
            f"{tenant_url}/api/v1/orgs",
            json={
                "name": f"integ-org-{suffix}",
                "slug": f"integ-org-{suffix}",
                "contact_email": f"test-{suffix}@example.com",
            },
        )
        assert resp.status_code == 201, f"Create org failed: {resp.text}"
        data = resp.json()
        assert data["name"] == f"integ-org-{suffix}"
        assert "id" in data

    async def test_list_organizations(self, http: httpx.AsyncClient, tenant_url):
        resp = await http.get(f"{tenant_url}/api/v1/orgs")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_create_and_get_organization(self, http: httpx.AsyncClient, tenant_url):
        suffix = uuid.uuid4().hex[:8]
        create_resp = await http.post(
            f"{tenant_url}/api/v1/orgs",
            json={
                "name": f"integ-get-{suffix}",
                "slug": f"integ-get-{suffix}",
                "contact_email": f"get-{suffix}@example.com",
            },
        )
        assert create_resp.status_code == 201
        org_id = create_resp.json()["id"]

        get_resp = await http.get(f"{tenant_url}/api/v1/orgs/{org_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == f"integ-get-{suffix}"

    async def test_update_organization(self, http: httpx.AsyncClient, tenant_url):
        suffix = uuid.uuid4().hex[:8]
        create_resp = await http.post(
            f"{tenant_url}/api/v1/orgs",
            json={
                "name": f"update-org-{suffix}",
                "slug": f"update-org-{suffix}",
                "contact_email": f"upd-{suffix}@example.com",
            },
        )
        assert create_resp.status_code == 201
        org_id = create_resp.json()["id"]

        patch_resp = await http.patch(
            f"{tenant_url}/api/v1/orgs/{org_id}",
            json={"name": f"updated-org-{suffix}", "tier": "STANDARD"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["name"] == f"updated-org-{suffix}"

    async def test_delete_organization(self, http: httpx.AsyncClient, tenant_url):
        suffix = uuid.uuid4().hex[:8]
        create_resp = await http.post(
            f"{tenant_url}/api/v1/orgs",
            json={
                "name": f"del-org-{suffix}",
                "slug": f"del-org-{suffix}",
                "contact_email": f"del-{suffix}@example.com",
            },
        )
        assert create_resp.status_code == 201
        org_id = create_resp.json()["id"]

        del_resp = await http.delete(f"{tenant_url}/api/v1/orgs/{org_id}")
        assert del_resp.status_code == 204

    async def test_duplicate_slug_rejected(self, http: httpx.AsyncClient, tenant_url):
        suffix = uuid.uuid4().hex[:8]
        slug = f"dup-slug-{suffix}"
        await http.post(
            f"{tenant_url}/api/v1/orgs",
            json={
                "name": f"dup-org-1-{suffix}",
                "slug": slug,
                "contact_email": f"dup1-{suffix}@example.com",
            },
        )
        resp = await http.post(
            f"{tenant_url}/api/v1/orgs",
            json={
                "name": f"dup-org-2-{suffix}",
                "slug": slug,
                "contact_email": f"dup2-{suffix}@example.com",
            },
        )
        assert resp.status_code in (409, 400), f"Expected conflict, got {resp.status_code}"


class TestTenantTeamCRUD:
    """Team CRUD within an organization."""

    async def _create_org(self, http, tenant_url):
        suffix = uuid.uuid4().hex[:8]
        resp = await http.post(
            f"{tenant_url}/api/v1/orgs",
            json={
                "name": f"team-org-{suffix}",
                "slug": f"team-org-{suffix}",
                "contact_email": f"team-{suffix}@example.com",
            },
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    async def test_create_team_in_org(self, http: httpx.AsyncClient, tenant_url):
        org_id = await self._create_org(http, tenant_url)
        suffix = uuid.uuid4().hex[:8]
        team_resp = await http.post(
            f"{tenant_url}/api/v1/orgs/{org_id}/teams",
            json={"name": f"team-{suffix}", "slug": f"team-{suffix}"},
        )
        assert team_resp.status_code == 201, f"Create team failed: {team_resp.text}"
        assert team_resp.json()["name"] == f"team-{suffix}"

    async def test_list_teams_in_org(self, http: httpx.AsyncClient, tenant_url):
        org_id = await self._create_org(http, tenant_url)

        # Create two teams
        for i in range(2):
            suffix = uuid.uuid4().hex[:8]
            await http.post(
                f"{tenant_url}/api/v1/orgs/{org_id}/teams",
                json={"name": f"list-team-{suffix}", "slug": f"list-team-{suffix}"},
            )

        resp = await http.get(f"{tenant_url}/api/v1/orgs/{org_id}/teams")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    async def test_delete_team(self, http: httpx.AsyncClient, tenant_url):
        org_id = await self._create_org(http, tenant_url)
        suffix = uuid.uuid4().hex[:8]
        team_resp = await http.post(
            f"{tenant_url}/api/v1/orgs/{org_id}/teams",
            json={"name": f"del-team-{suffix}", "slug": f"del-team-{suffix}"},
        )
        assert team_resp.status_code == 201
        team_id = team_resp.json()["id"]

        del_resp = await http.delete(f"{tenant_url}/api/v1/orgs/{org_id}/teams/{team_id}")
        assert del_resp.status_code == 204


class TestTenantProjectCRUD:
    """Project CRUD within a team."""

    async def test_full_hierarchy(self, http: httpx.AsyncClient, tenant_url):
        """Create org → team → project and verify the full hierarchy."""
        suffix = uuid.uuid4().hex[:8]

        # Create org
        org_resp = await http.post(
            f"{tenant_url}/api/v1/orgs",
            json={
                "name": f"proj-org-{suffix}",
                "slug": f"proj-org-{suffix}",
                "contact_email": f"proj-{suffix}@example.com",
            },
        )
        assert org_resp.status_code == 201
        org_id = org_resp.json()["id"]

        # Create team
        team_resp = await http.post(
            f"{tenant_url}/api/v1/orgs/{org_id}/teams",
            json={"name": f"proj-team-{suffix}", "slug": f"proj-team-{suffix}"},
        )
        assert team_resp.status_code == 201
        team_id = team_resp.json()["id"]

        # Create project
        proj_resp = await http.post(
            f"{tenant_url}/api/v1/orgs/{org_id}/teams/{team_id}/projects",
            json={"name": f"proj-{suffix}", "slug": f"proj-{suffix}"},
        )
        assert proj_resp.status_code == 201
        proj_data = proj_resp.json()
        assert proj_data["name"] == f"proj-{suffix}"

        # List projects in team
        list_resp = await http.get(
            f"{tenant_url}/api/v1/orgs/{org_id}/teams/{team_id}/projects"
        )
        assert list_resp.status_code == 200
        assert any(p["name"] == f"proj-{suffix}" for p in list_resp.json())
