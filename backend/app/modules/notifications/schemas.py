"""Граница контракта модуля notifications."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.enums import NotificationType
from app.core.pagination import Page


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    type: NotificationType
    task_id: UUID | None
    comment_id: UUID | None
    actor_id: UUID
    read_at: datetime | None
    created_at: datetime


class NotificationPage(Page[NotificationRead]):
    pass
