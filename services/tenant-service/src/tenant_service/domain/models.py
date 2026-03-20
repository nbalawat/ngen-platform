from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class TenantTier(StrEnum):
    FREE = "FREE"
    STANDARD = "STANDARD"
    ENTERPRISE = "ENTERPRISE"


class TenantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    PENDING = "PENDING"
    DEACTIVATED = "DEACTIVATED"


_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$")


def _validate_slug(v: str) -> str:
    if not _SLUG_PATTERN.match(v):
        msg = "slug must be lowercase alphanumeric with hyphens, cannot start/end with hyphen"
        raise ValueError(msg)
    return v


def _utc_now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------


class Organization(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=3, max_length=100)
    slug: str = Field(min_length=3, max_length=60)
    tier: TenantTier = TenantTier.FREE
    status: TenantStatus = TenantStatus.PENDING
    contact_email: str
    max_agents: int = 10
    max_teams: int = 5
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: str) -> str:
        return _validate_slug(v)


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    slug: str = Field(min_length=3, max_length=60)
    tier: TenantTier = TenantTier.FREE
    contact_email: str
    max_agents: int = 10
    max_teams: int = 5
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: str) -> str:
        return _validate_slug(v)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=100)
    tier: TenantTier | None = None
    status: TenantStatus | None = None
    contact_email: str | None = None
    max_agents: int | None = None
    max_teams: int | None = None
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------


class Team(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    org_id: UUID
    name: str = Field(min_length=3, max_length=100)
    slug: str = Field(min_length=3, max_length=60)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: str) -> str:
        return _validate_slug(v)


class TeamCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    slug: str = Field(min_length=3, max_length=60)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: str) -> str:
        return _validate_slug(v)


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=100)
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


class Project(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    team_id: UUID
    name: str = Field(min_length=3, max_length=100)
    slug: str = Field(min_length=3, max_length=60)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: str) -> str:
        return _validate_slug(v)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    slug: str = Field(min_length=3, max_length=60)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: str) -> str:
        return _validate_slug(v)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=100)
    metadata: dict[str, Any] | None = None
