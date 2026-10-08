"""Комментарии к задачам и упоминания в них."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.core.database import Base


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        Index(
            "idx_comments_task",
            "task_id",
            "created_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Заполнен, если комментарий оставил агент: видно, через какой токен.
    author_token_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("api_tokens.id", ondelete="SET NULL")
    )
    # Один уровень ответов: родитель — всегда комментарий верхнего уровня.
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("comments.id", ondelete="CASCADE")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class CommentMention(Base):
    """Упоминания материализованы: «где меня упомянули» — индексный запрос."""

    __tablename__ = "comment_mentions"

    comment_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("comments.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
