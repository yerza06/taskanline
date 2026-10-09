"""Сохранённые срезы задач."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.core.database import Base
from app.core.enums import SortDirection, ViewGroupBy, ViewLayout, ViewScope, ViewSortBy


class View(Base):
    __tablename__ = "views"
    __table_args__ = (
        # Владелец и команда заполнены ровно тогда, когда того требует scope.
        CheckConstraint(
            "(scope = 'user' AND owner_id IS NOT NULL AND team_id IS NULL)"
            " OR (scope = 'team' AND team_id IS NOT NULL AND owner_id IS NULL)"
            " OR (scope = 'workspace' AND team_id IS NULL AND owner_id IS NULL)",
            name="view_scope",
        ),
        CheckConstraint(
            "group_by IS NULL OR group_by IN"
            " ('state', 'assignee', 'priority', 'project', 'label', 'due_date')",
            name="group_by",
        ),
        CheckConstraint(
            "sort_by IN ('manual', 'priority', 'due_date', 'created_at', 'updated_at', 'title')",
            name="sort_by",
        ),
        CheckConstraint("sort_direction IN ('asc', 'desc')", name="sort_direction"),
        CheckConstraint("layout IN ('list', 'board')", name="layout"),
        CheckConstraint("color IS NULL OR color ~ '^#[0-9a-fA-F]{6}$'", name="color_format"),
        Index("idx_views_user", "owner_id", "position", postgresql_where=text("scope = 'user'")),
        Index("idx_views_team", "team_id", "position", postgresql_where=text("scope = 'team'")),
        Index(
            "idx_views_workspace",
            "workspace_id",
            "position",
            postgresql_where=text("scope = 'workspace'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[ViewScope] = mapped_column(String(16), nullable=False)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    team_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(7))
    # Грамматика — §4 модели данных; проверяется при сохранении и повторно при выполнении.
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    group_by: Mapped[ViewGroupBy | None] = mapped_column(String(24))
    sort_by: Mapped[ViewSortBy] = mapped_column(
        String(24), nullable=False, server_default="manual", default=ViewSortBy.MANUAL
    )
    sort_direction: Mapped[SortDirection] = mapped_column(
        String(4), nullable=False, server_default="asc", default=SortDirection.ASC
    )
    layout: Mapped[ViewLayout] = mapped_column(
        String(16), nullable=False, server_default="list", default=ViewLayout.LIST
    )
    # Порядок в боковом меню внутри своего scope.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
