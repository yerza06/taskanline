"""Входящие уведомления. Доставка только внутри приложения: писем и пушей нет."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.core.database import Base
from app.core.enums import NotificationType


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "type IN ('mentioned', 'assigned', 'commented', 'state_changed')", name="type"
        ),
        Index(
            "idx_notifications_inbox",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    # Получатель.
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[NotificationType] = mapped_column(String(32), nullable=False)
    task_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("tasks.id", ondelete="CASCADE"))
    comment_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("comments.id", ondelete="CASCADE")
    )
    actor_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
