from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tenant_service.domain.models import (
    Organization,
    OrganizationCreate,
    OrganizationUpdate,
    Project,
    ProjectCreate,
    Team,
    TeamCreate,
)
from tenant_service.infrastructure.database import get_db
from tenant_service.infrastructure.repository import TenantRepository

router = APIRouter(prefix="/api/v1")


def _repo(session: Annotated[AsyncSession, Depends(get_db)]) -> TenantRepository:
    return TenantRepository(session)


RepoDep = Annotated[TenantRepository, Depends(_repo)]


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------


@router.post(
    "/orgs", response_model=Organization, status_code=status.HTTP_201_CREATED
)
async def create_org(body: OrganizationCreate, repo: RepoDep) -> Organization:
    try:
        return await repo.create_org(body)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Organization slug '{body.slug}' already exists",
        ) from exc


@router.get("/orgs", response_model=list[Organization])
async def list_orgs(
    repo: RepoDep, offset: int = 0, limit: int = 50
) -> list[Organization]:
    return await repo.list_orgs(offset=offset, limit=limit)


@router.get("/orgs/{org_id}", response_model=Organization)
async def get_org(org_id: UUID, repo: RepoDep) -> Organization:
    org = await repo.get_org(org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return org


@router.patch("/orgs/{org_id}", response_model=Organization)
async def update_org(
    org_id: UUID, body: OrganizationUpdate, repo: RepoDep
) -> Organization:
    org = await repo.update_org(org_id, body)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return org


@router.delete("/orgs/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org(org_id: UUID, repo: RepoDep) -> None:
    deleted = await repo.delete_org(org_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


@router.post(
    "/orgs/{org_id}/teams",
    response_model=Team,
    status_code=status.HTTP_201_CREATED,
)
async def create_team(
    org_id: UUID, body: TeamCreate, repo: RepoDep
) -> Team:
    org = await repo.get_org(org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    try:
        return await repo.create_team(org_id, body)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Team slug '{body.slug}' already exists in this organization"
            ),
        ) from exc


@router.get("/orgs/{org_id}/teams", response_model=list[Team])
async def list_teams(
    org_id: UUID, repo: RepoDep, offset: int = 0, limit: int = 50
) -> list[Team]:
    return await repo.list_teams(org_id, offset=offset, limit=limit)


@router.get("/orgs/{org_id}/teams/{team_id}", response_model=Team)
async def get_team(org_id: UUID, team_id: UUID, repo: RepoDep) -> Team:
    team = await repo.get_team(org_id, team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
        )
    return team


@router.delete(
    "/orgs/{org_id}/teams/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_team(
    org_id: UUID, team_id: UUID, repo: RepoDep
) -> None:
    deleted = await repo.delete_team(org_id, team_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
        )


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@router.post(
    "/orgs/{org_id}/teams/{team_id}/projects",
    response_model=Project,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    org_id: UUID, team_id: UUID, body: ProjectCreate, repo: RepoDep
) -> Project:
    team = await repo.get_team(org_id, team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Team not found"
        )
    try:
        return await repo.create_project(team_id, body)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Project slug '{body.slug}' already exists in this team"
            ),
        ) from exc


@router.get(
    "/orgs/{org_id}/teams/{team_id}/projects",
    response_model=list[Project],
)
async def list_projects(
    org_id: UUID,
    team_id: UUID,
    repo: RepoDep,
    offset: int = 0,
    limit: int = 50,
) -> list[Project]:
    return await repo.list_projects(team_id, offset=offset, limit=limit)


@router.get(
    "/orgs/{org_id}/teams/{team_id}/projects/{project_id}",
    response_model=Project,
)
async def get_project(
    org_id: UUID, team_id: UUID, project_id: UUID, repo: RepoDep
) -> Project:
    project = await repo.get_project(team_id, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


@router.delete(
    "/orgs/{org_id}/teams/{team_id}/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project(
    org_id: UUID, team_id: UUID, project_id: UUID, repo: RepoDep
) -> None:
    deleted = await repo.delete_project(team_id, project_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
