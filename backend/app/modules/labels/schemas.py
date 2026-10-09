"""Граница контракта модуля labels."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.schemas import reject_control_characters, reject_explicit_null
from app.modules.states.schemas import COLOR_PATTERN


class LabelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    # Не указан — метка общая для всего workspace.
    team_id: UUID | None = None
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(pattern=COLOR_PATTERN)

    _name = field_validator("name", mode="before")(reject_control_characters)


class LabelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)

    _name = field_validator("name", mode="before")(reject_control_characters)

    @model_validator(mode="after")
    def _required_stay_set(self) -> Self:
        reject_explicit_null(self, "name", "color")
        return self


class LabelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    team_id: UUID | None
    name: str
    color: str
    created_at: datetime


class LabelList(BaseModel):
    items: list[LabelRead]
