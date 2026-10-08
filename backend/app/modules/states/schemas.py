"""Граница контракта модуля states."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import StateType
from app.core.schemas import reject_control_characters, reject_explicit_null

COLOR_PATTERN = r"^#[0-9a-fA-F]{6}$"


class StateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    type: StateType
    color: str = Field(pattern=COLOR_PATTERN)
    # Не указан — статус встаёт последней колонкой.
    position: int | None = Field(default=None, ge=0)
    is_default: bool = False

    _name = field_validator("name", mode="before")(reject_control_characters)


class StateUpdate(BaseModel):
    """Тип статуса не меняется: на нём держатся started_at/completed_at уже лежащих задач."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    position: int | None = Field(default=None, ge=0)
    is_default: bool | None = None

    _name = field_validator("name", mode="before")(reject_control_characters)

    @model_validator(mode="after")
    def _required_stay_set(self) -> Self:
        reject_explicit_null(self, "name", "color", "position", "is_default")
        return self


class StateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    team_id: UUID
    name: str
    type: StateType
    color: str
    position: int
    is_default: bool
    created_at: datetime


class StateList(BaseModel):
    items: list[StateRead]
