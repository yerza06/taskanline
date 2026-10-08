"""История изменений задач. Append-only: строки не обновляются и не удаляются."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.core.database import Base
from app.core.enums import ActivityType

ACTIVITY_TYPES_CHECK = "type IN ({})".format(", ".join(f"'{kind}'" for kind in ActivityType))


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        CheckConstraint(ACTIVITY_TYPES_CHECK, name="type"),
        Index("idx_activities_task", "task_id", text("created_at DESC")),
        Index("idx_activities_ws", "workspace_id", text("created_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("tasks.id", ondelete="CASCADE"))
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE")
    )
    actor_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Через какой токен, если действовал агент: без этого его не отличить от человека.
    actor_token_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("api_tokens.id", ondelete="SET NULL")
    )
    type: Mapped[ActivityType] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
