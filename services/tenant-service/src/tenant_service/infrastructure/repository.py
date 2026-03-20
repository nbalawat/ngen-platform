from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tenant_service.domain.models import (
    Organization,
    OrganizationCreate,
    OrganizationUpdate,
    Project,
    ProjectCreate,
    ProjectUpdate,
    Team,
    TeamCreate,
    TeamUpdate,
)
from tenant_service.infrastructure.database import (
    OrganizationRow,
    ProjectRow,
    TeamRow,
)


def _org_from_row(row: OrganizationRow) -> Organization:
    return Organization(
        id=row.id,
        name=row.name,
        slug=row.slug,
        tier=row.tier,
        status=row.status,
        contact_email=row.contact_email,
        max_agents=row.max_agents,
        max_teams=row.max_teams,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata=row.metadata_,
    )


def _team_from_row(row: TeamRow) -> Team:
    return Team(
        id=row.id,
        org_id=row.org_id,
        name=row.name,
        slug=row.slug,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata=row.metadata_,
    )


def _project_from_row(row: ProjectRow) -> Project:
    return Project(
        id=row.id,
        team_id=row.team_id,
        name=row.name,
        slug=row.slug,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata=row.metadata_,
    )


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -------------------------------------------------------------------
    # Organizations
    # -------------------------------------------------------------------

    async def create_org(self, data: OrganizationCreate) -> Organization:
        row = OrganizationRow(
            name=data.name,
            slug=data.slug,
            tier=data.tier.value,
            contact_email=data.contact_email,
            max_agents=data.max_agents,
            max_teams=data.max_teams,
            metadata_=data.metadata,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _org_from_row(row)

    async def get_org(self, org_id: UUID) -> Organization | None:
        row = await self._session.get(OrganizationRow, org_id)
        return _org_from_row(row) if row else None

    async def get_org_by_slug(self, slug: str) -> Organization | None:
        stmt = select(OrganizationRow).where(OrganizationRow.slug == slug)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _org_from_row(row) if row else None

    async def list_orgs(
        self, *, offset: int = 0, limit: int = 50
    ) -> list[Organization]:
        stmt = (
            select(OrganizationRow)
            .order_by(OrganizationRow.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_org_from_row(r) for r in rows]

    async def update_org(
        self, org_id: UUID, data: OrganizationUpdate
    ) -> Organization | None:
        values: dict[str, Any] = {}
        update_data = data.model_dump(exclude_unset=True)
        for key, val in update_data.items():
            if key == "metadata":
                values["metadata_"] = val
            elif key in ("tier", "status"):
                values[key] = val.value if val is not None else val
            else:
                values[key] = val
        if not values:
            return await self.get_org(org_id)
        values["updated_at"] = datetime.now(UTC)
        stmt = (
            update(OrganizationRow)
            .where(OrganizationRow.id == org_id)
            .values(**values)
        )
        result = await self._session.execute(stmt)
        if result.rowcount == 0:
            return None
        return await self.get_org(org_id)

    async def delete_org(self, org_id: UUID) -> bool:
        stmt = delete(OrganizationRow).where(OrganizationRow.id == org_id)
        result = await self._session.execute(stmt)
        return result.rowcount > 0

    # -------------------------------------------------------------------
    # Teams
    # -------------------------------------------------------------------

    async def create_team(self, org_id: UUID, data: TeamCreate) -> Team:
        row = TeamRow(
            org_id=org_id,
            name=data.name,
            slug=data.slug,
            metadata_=data.metadata,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _team_from_row(row)

    async def get_team(self, org_id: UUID, team_id: UUID) -> Team | None:
        stmt = select(TeamRow).where(
            TeamRow.id == team_id, TeamRow.org_id == org_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _team_from_row(row) if row else None

    async def list_teams(
        self, org_id: UUID, *, offset: int = 0, limit: int = 50
    ) -> list[Team]:
        stmt = (
            select(TeamRow)
            .where(TeamRow.org_id == org_id)
            .order_by(TeamRow.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_team_from_row(r) for r in rows]

    async def update_team(
        self, org_id: UUID, team_id: UUID, data: TeamUpdate
    ) -> Team | None:
        values: dict[str, Any] = {}
        update_data = data.model_dump(exclude_unset=True)
        for key, val in update_data.items():
            if key == "metadata":
                values["metadata_"] = val
            else:
                values[key] = val
        if not values:
            return await self.get_team(org_id, team_id)
        values["updated_at"] = datetime.now(UTC)
        stmt = (
            update(TeamRow)
            .where(TeamRow.id == team_id, TeamRow.org_id == org_id)
            .values(**values)
        )
        result = await self._session.execute(stmt)
        if result.rowcount == 0:
            return None
        return await self.get_team(org_id, team_id)

    async def delete_team(self, org_id: UUID, team_id: UUID) -> bool:
        stmt = delete(TeamRow).where(
            TeamRow.id == team_id, TeamRow.org_id == org_id
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0

    # -------------------------------------------------------------------
    # Projects
    # -------------------------------------------------------------------

    async def create_project(self, team_id: UUID, data: ProjectCreate) -> Project:
        row = ProjectRow(
            team_id=team_id,
            name=data.name,
            slug=data.slug,
            metadata_=data.metadata,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _project_from_row(row)

    async def get_project(self, team_id: UUID, project_id: UUID) -> Project | None:
        stmt = select(ProjectRow).where(
            ProjectRow.id == project_id, ProjectRow.team_id == team_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _project_from_row(row) if row else None

    async def list_projects(
        self, team_id: UUID, *, offset: int = 0, limit: int = 50
    ) -> list[Project]:
        stmt = (
            select(ProjectRow)
            .where(ProjectRow.team_id == team_id)
            .order_by(ProjectRow.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_project_from_row(r) for r in rows]

    async def update_project(
        self, team_id: UUID, project_id: UUID, data: ProjectUpdate
    ) -> Project | None:
        values: dict[str, Any] = {}
        update_data = data.model_dump(exclude_unset=True)
        for key, val in update_data.items():
            if key == "metadata":
                values["metadata_"] = val
            else:
                values[key] = val
        if not values:
            return await self.get_project(team_id, project_id)
        values["updated_at"] = datetime.now(UTC)
        stmt = (
            update(ProjectRow)
            .where(ProjectRow.id == project_id, ProjectRow.team_id == team_id)
            .values(**values)
        )
        result = await self._session.execute(stmt)
        if result.rowcount == 0:
            return None
        return await self.get_project(team_id, project_id)

    async def delete_project(self, team_id: UUID, project_id: UUID) -> bool:
        stmt = delete(ProjectRow).where(
            ProjectRow.id == project_id, ProjectRow.team_id == team_id
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0
