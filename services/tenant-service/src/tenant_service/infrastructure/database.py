from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, MetaData, String, UniqueConstraint, Uuid
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tenant_service.config import settings

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class OrganizationRow(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="FREE")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    max_agents: Mapped[int] = mapped_column(default=10)
    max_teams: Mapped[int] = mapped_column(default=5)
    created_at: Mapped[datetime] = mapped_column(default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=_utc_now, onupdate=_utc_now)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )


class TeamRow(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_teams_org_id_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=_utc_now, onupdate=_utc_now)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )


class ProjectRow(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("team_id", "slug", name="uq_projects_team_id_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=_utc_now, onupdate=_utc_now)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )


def create_engine(url: str | None = None, **kwargs: Any):
    defaults = {"echo": settings.DEBUG}
    if "sqlite" not in (url or settings.DATABASE_URL):
        defaults["pool_size"] = 5
        defaults["max_overflow"] = 10
    defaults.update(kwargs)
    return create_async_engine(url or settings.DATABASE_URL, **defaults)


_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(), expire_on_commit=False
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
