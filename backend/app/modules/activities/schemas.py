"""Граница контракта модуля activities."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.enums import ActivityType
from app.core.pagination import Page


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID | None
    actor_id: UUID
    # Заполнен, когда действовал агент: через какой токен.
    actor_token_id: UUID | None
    type: ActivityType
    payload: dict[str, Any]
    created_at: datetime


class ActivityPage(Page[ActivityRead]):
    pass
