"""Рабочие пространства и участие в них.

`workspace_members` — корень всей модели прав: членства в командах и проектах
ссылаются на неё составным ключом и исчезают вместе с ней.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.core.database import Base
from app.core.enums import WorkspaceRole


class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (Index("idx_workspaces_slug", "slug", unique=True),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # CITEXT: `Acme` и `acme` — один адрес в URL.
    slug: Mapped[str] = mapped_column(CITEXT, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    # RESTRICT: пользователя, создавшего пространство, нельзя удалить молча.
    created_by: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'admin', 'member', 'guest')", name="role"),
        # На этот индекс опираются составные FK из team_members и project_members.
        Index("idx_ws_members_unique", "workspace_id", "user_id", unique=True),
        Index("idx_ws_members_user", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[WorkspaceRole] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
