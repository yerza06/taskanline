"""Граница контракта модуля comments."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.pagination import Page


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=20_000, description="Markdown; @email — упоминание")
    # Ответ — только на комментарий верхнего уровня.
    parent_id: UUID | None = None


class CommentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=20_000)


class CommentRead(BaseModel):
    id: UUID
    task_id: UUID
    author_id: UUID
    # Заполнен, если комментарий оставил агент.
    author_token_id: UUID | None
    parent_id: UUID | None
    body: str
    mention_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


class CommentPage(Page[CommentRead]):
    pass
