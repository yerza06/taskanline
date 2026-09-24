"""Граница контракта модуля teams."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import TeamRole
from app.core.schemas import reject_explicit_null
from app.modules.workspaces.schemas import MemberRead

KEY_PATTERN = r"^[A-Z]{2,5}$"


def normalize_key(value: object) -> object:
    """Ключ хранится в верхнем регистре: `eng` и `ENG` — одна команда."""
    return value.strip().upper() if isinstance(value, str) else value


class TeamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=KEY_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    is_private: bool = False

    _key = field_validator("key", mode="before")(normalize_key)


class TeamUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str | None = Field(default=None, pattern=KEY_PATTERN)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    is_private: bool | None = None

    _key = field_validator("key", mode="before")(normalize_key)

    @model_validator(mode="after")
    def _required_stay_set(self) -> Self:
        reject_explicit_null(self, "key", "name", "is_private")
        return self


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    key: str
    name: str
    description: str | None
    is_private: bool
    created_at: datetime
    updated_at: datetime


class TeamList(BaseModel):
    items: list[TeamRead]


class TeamMemberRead(MemberRead):
    role: TeamRole


class TeamMemberList(BaseModel):
    items: list[TeamMemberRead]


class TeamMemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: TeamRole
