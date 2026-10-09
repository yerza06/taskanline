"""Команды и участие в них."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.core.database import Base
from app.core.enums import TeamRole


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        # Ключ — часть идентификатора задачи (`ENG-142`); хранится в верхнем регистре.
        CheckConstraint("key ~ '^[A-Z]{2,5}$'", name="key_format"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(5), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Приватную команду рядовой участник workspace не видит вовсе.
    is_private: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    # Счётчик номеров задач: выдаётся UPDATE … RETURNING на этапе 3.
    task_counter: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


# Функциональный индекс объявляется снаружи класса: ему нужно выражение над колонкой.
Index("idx_teams_key", Team.workspace_id, func.upper(Team.key), unique=True)


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        CheckConstraint("role IN ('lead', 'member')", name="role"),
        # Составной ключ на workspace_members: без членства в пространстве нет и
        # членства в команде, а исключение из пространства снимает его само.
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["workspace_members.workspace_id", "workspace_members.user_id"],
            name="fk_team_members_workspace_member",
            ondelete="CASCADE",
        ),
        Index("idx_team_members_unique", "team_id", "user_id", unique=True),
        Index("idx_team_members_lookup", "user_id", "workspace_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # Денормализация: изоляция по workspace_id — свойство самого запроса.
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    team_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    role: Mapped[TeamRole] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
