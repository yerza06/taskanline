"""Метки уровня команды и уровня workspace."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.core.database import Base


class Label(Base):
    __tablename__ = "labels"
    __table_args__ = (CheckConstraint("color ~ '^#[0-9a-fA-F]{6}$'", name="color_format"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    # NULL — метка общая для всего workspace.
    team_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


Index(
    "idx_labels_ws",
    Label.workspace_id,
    func.lower(Label.name),
    unique=True,
    postgresql_where=text("team_id IS NULL"),
)
Index(
    "idx_labels_team",
    Label.team_id,
    func.lower(Label.name),
    unique=True,
    postgresql_where=text("team_id IS NOT NULL"),
)


class TaskLabel(Base):
    __tablename__ = "task_labels"
    __table_args__ = (Index("idx_task_labels_label", "label_id", "task_id"),)

    task_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    label_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True
    )
    # Для единообразия фильтрации: изоляция — свойство запроса.
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
