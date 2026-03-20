from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from tenant_service.domain.models import (
    OrganizationCreate,
    OrganizationUpdate,
    ProjectCreate,
    TeamCreate,
)
from tenant_service.infrastructure.repository import (
    TenantRepository,
)


def _make_org_create(
    slug: str = "test-org",
) -> OrganizationCreate:
    return OrganizationCreate(
        name="Test Organization",
        slug=slug,
        contact_email="test@org.com",
    )


# ---------------------------------------------------------------------------
# Organization tests
# ---------------------------------------------------------------------------


async def test_create_and_get_org(
    db_session: AsyncSession,
):
    repo = TenantRepository(db_session)
    created = await repo.create_org(_make_org_create())

    assert created.slug == "test-org"
    assert created.id is not None

    fetched = await repo.get_org(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "Test Organization"


async def test_get_org_not_found_returns_none(
    db_session: AsyncSession,
):
    repo = TenantRepository(db_session)
    result = await repo.get_org(uuid4())
    assert result is None


async def test_list_orgs_empty(
    db_session: AsyncSession,
):
    repo = TenantRepository(db_session)
    orgs = await repo.list_orgs()
    assert orgs == []


async def test_list_orgs_multiple(
    db_session: AsyncSession,
):
    repo = TenantRepository(db_session)
    await repo.create_org(_make_org_create(slug="org-one"))
    await repo.create_org(_make_org_create(slug="org-two"))
    await db_session.flush()

    orgs = await repo.list_orgs()
    assert len(orgs) == 2
    slugs = {o.slug for o in orgs}
    assert slugs == {"org-one", "org-two"}


async def test_update_org(db_session: AsyncSession):
    repo = TenantRepository(db_session)
    created = await repo.create_org(_make_org_create())

    updated = await repo.update_org(
        created.id, OrganizationUpdate(name="Renamed Org")
    )
    assert updated is not None
    assert updated.name == "Renamed Org"
    assert updated.id == created.id


async def test_delete_org(db_session: AsyncSession):
    repo = TenantRepository(db_session)
    created = await repo.create_org(_make_org_create())

    deleted = await repo.delete_org(created.id)
    assert deleted is True

    fetched = await repo.get_org(created.id)
    assert fetched is None


# ---------------------------------------------------------------------------
# Team tests
# ---------------------------------------------------------------------------


async def test_create_team_for_org(
    db_session: AsyncSession,
):
    repo = TenantRepository(db_session)
    org = await repo.create_org(_make_org_create())

    team_data = TeamCreate(
        name="Engineering", slug="engineering"
    )
    team = await repo.create_team(org.id, team_data)
    assert team.name == "Engineering"
    assert team.org_id == org.id


async def test_list_teams_scoped_to_org(
    db_session: AsyncSession,
):
    repo = TenantRepository(db_session)
    org_a = await repo.create_org(
        _make_org_create(slug="org-a")
    )
    org_b = await repo.create_org(
        _make_org_create(slug="org-b")
    )

    await repo.create_team(
        org_a.id,
        TeamCreate(name="Team Alpha", slug="team-alpha"),
    )
    await repo.create_team(
        org_b.id,
        TeamCreate(name="Team Beta", slug="team-beta"),
    )
    await db_session.flush()

    teams_a = await repo.list_teams(org_a.id)
    assert len(teams_a) == 1
    assert teams_a[0].name == "Team Alpha"

    teams_b = await repo.list_teams(org_b.id)
    assert len(teams_b) == 1
    assert teams_b[0].name == "Team Beta"


# ---------------------------------------------------------------------------
# Project tests
# ---------------------------------------------------------------------------


async def test_create_project_for_team(
    db_session: AsyncSession,
):
    repo = TenantRepository(db_session)
    org = await repo.create_org(_make_org_create())

    team_data = TeamCreate(
        name="Platform", slug="platform"
    )
    team = await repo.create_team(org.id, team_data)

    proj_data = ProjectCreate(
        name="Auth Module", slug="auth-module"
    )
    project = await repo.create_project(
        team.id, proj_data
    )
    assert project.name == "Auth Module"
    assert project.team_id == team.id
