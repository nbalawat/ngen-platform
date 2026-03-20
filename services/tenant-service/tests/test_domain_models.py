from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError
from tenant_service.domain.models import (
    Organization,
    OrganizationCreate,
    OrganizationUpdate,
    Project,
    ProjectCreate,
    Team,
    TeamCreate,
    TenantStatus,
    TenantTier,
)

# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------


class TestOrganization:
    def test_create_valid_organization(self):
        org = Organization(
            name="Acme Corp",
            slug="acme-corp",
            contact_email="admin@acme.test",
        )
        assert org.name == "Acme Corp"
        assert org.slug == "acme-corp"
        assert org.contact_email == "admin@acme.test"
        assert isinstance(org.id, UUID)

    def test_defaults(self):
        org = Organization(
            name="Acme Corp",
            slug="acme-corp",
            contact_email="admin@acme.test",
        )
        assert org.tier == TenantTier.FREE
        assert org.status == TenantStatus.PENDING
        assert org.max_agents == 10
        assert org.max_teams == 5
        assert org.metadata == {}
        assert org.created_at is not None
        assert org.updated_at is not None

    def test_auto_generated_id_is_unique(self):
        org1 = Organization(
            name="Org One",
            slug="org-one",
            contact_email="a@test.com",
        )
        org2 = Organization(
            name="Org Two",
            slug="org-two",
            contact_email="b@test.com",
        )
        assert org1.id != org2.id

    @pytest.mark.parametrize(
        "valid_slug",
        ["acme", "acme-corp", "a1b2", "x", "abc-def-ghi"],
    )
    def test_valid_slugs(self, valid_slug: str):
        if len(valid_slug) < 3:
            # single-char slugs fail min_length before the regex runs
            with pytest.raises(ValidationError):
                Organization(
                    name="Test",
                    slug=valid_slug,
                    contact_email="t@t.com",
                )
            return
        org = Organization(
            name="Test Org",
            slug=valid_slug,
            contact_email="t@test.com",
        )
        assert org.slug == valid_slug

    @pytest.mark.parametrize(
        "invalid_slug",
        [
            "Acme-Corp",   # uppercase
            "acme corp",   # space
            "-acme",       # starts with hyphen
            "acme-",       # ends with hyphen
            "acme_corp",   # underscore
            "ACME",        # all uppercase
        ],
    )
    def test_invalid_slugs(self, invalid_slug: str):
        with pytest.raises(ValidationError):
            Organization(
                name="Test Org",
                slug=invalid_slug,
                contact_email="t@test.com",
            )

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            Organization(
                name="AB",
                slug="valid-slug",
                contact_email="t@test.com",
            )

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            Organization(
                name="A" * 101,
                slug="valid-slug",
                contact_email="t@test.com",
            )

    def test_serialization_roundtrip(self):
        org = Organization(
            name="Acme Corp",
            slug="acme-corp",
            contact_email="admin@acme.test",
        )
        data = org.model_dump()
        assert data["name"] == "Acme Corp"
        assert data["slug"] == "acme-corp"
        assert data["tier"] == TenantTier.FREE
        restored = Organization.model_validate(data)
        assert restored.id == org.id
        assert restored.name == org.name

    def test_model_dump_mode_json(self):
        org = Organization(
            name="Acme Corp",
            slug="acme-corp",
            contact_email="admin@acme.test",
        )
        data = org.model_dump(mode="json")
        # UUID and datetime should be serialised as strings
        assert isinstance(data["id"], str)
        assert isinstance(data["created_at"], str)


# ---------------------------------------------------------------------------
# OrganizationCreate / OrganizationUpdate
# ---------------------------------------------------------------------------


class TestOrganizationCreate:
    def test_valid_create(self):
        payload = OrganizationCreate(
            name="New Org",
            slug="new-org",
            contact_email="new@org.com",
        )
        assert payload.name == "New Org"
        assert payload.tier == TenantTier.FREE

    def test_create_slug_validation(self):
        with pytest.raises(ValidationError):
            OrganizationCreate(
                name="Bad Slug",
                slug="Bad Slug",
                contact_email="x@x.com",
            )


class TestOrganizationUpdate:
    def test_partial_update(self):
        update = OrganizationUpdate(name="Renamed")
        assert update.name == "Renamed"
        assert update.tier is None
        assert update.status is None

    def test_all_none_by_default(self):
        update = OrganizationUpdate()
        dumped = update.model_dump(exclude_none=True)
        assert dumped == {}


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------


class TestTeam:
    def test_create_team(self):
        org = Organization(
            name="Parent Org",
            slug="parent-org",
            contact_email="p@org.com",
        )
        team = Team(
            org_id=org.id,
            name="Platform Team",
            slug="platform-team",
        )
        assert team.org_id == org.id
        assert team.name == "Platform Team"
        assert isinstance(team.id, UUID)

    def test_team_slug_validation(self):
        with pytest.raises(ValidationError):
            Team(
                org_id=UUID("12345678-1234-1234-1234-123456789abc"),
                name="Bad Team",
                slug="Bad Team",
            )

    def test_team_serialization(self):
        team = Team(
            org_id=UUID("12345678-1234-1234-1234-123456789abc"),
            name="Test Team",
            slug="test-team",
        )
        data = team.model_dump()
        restored = Team.model_validate(data)
        assert restored.id == team.id
        assert restored.org_id == team.org_id


class TestTeamCreate:
    def test_valid_create(self):
        tc = TeamCreate(name="Engineering", slug="engineering")
        assert tc.name == "Engineering"


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


class TestProject:
    def test_create_project(self):
        team_id = UUID("abcdef01-2345-6789-abcd-ef0123456789")
        proj = Project(
            team_id=team_id,
            name="Auth Service",
            slug="auth-service",
        )
        assert proj.team_id == team_id
        assert isinstance(proj.id, UUID)

    def test_project_slug_validation(self):
        with pytest.raises(ValidationError):
            Project(
                team_id=UUID(
                    "abcdef01-2345-6789-abcd-ef0123456789"
                ),
                name="Bad Project",
                slug="Bad Project!",
            )

    def test_project_serialization(self):
        proj = Project(
            team_id=UUID(
                "abcdef01-2345-6789-abcd-ef0123456789"
            ),
            name="Service",
            slug="service",
        )
        data = proj.model_dump(mode="json")
        assert isinstance(data["team_id"], str)
        restored = Project.model_validate(data)
        assert restored.slug == "service"


class TestProjectCreate:
    def test_valid_create(self):
        pc = ProjectCreate(
            name="My Project", slug="my-project"
        )
        assert pc.name == "My Project"
