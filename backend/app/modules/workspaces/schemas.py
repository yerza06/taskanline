"""Граница контракта модуля workspaces."""

from datetime import datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import WorkspaceRole
from app.core.schemas import reject_explicit_null
from app.modules.users.models import User

SLUG_PATTERN = r"^[a-z0-9-]{2,40}$"


def normalize_slug(value: object) -> object:
    """Slug хранится в нижнем регистре: в URL `Acme` и `acme` — один адрес."""
    return value.strip().lower() if isinstance(value, str) else value


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=SLUG_PATTERN)

    _slug = field_validator("slug", mode="before")(normalize_slug)


class WorkspaceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)
    avatar_url: str | None = Field(default=None, max_length=2000)

    _slug = field_validator("slug", mode="before")(normalize_slug)

    @model_validator(mode="after")
    def _required_stay_set(self) -> Self:
        reject_explicit_null(self, "name", "slug")
        return self


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    avatar_url: str | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class WorkspaceList(BaseModel):
    items: list[WorkspaceRead]


class MemberRead(BaseModel):
    """Участник любого уровня: человек и момент, с которого он там числится."""

    user_id: UUID
    email: str
    full_name: str
    avatar_url: str | None
    joined_at: datetime


def member_fields(user: User, joined_at: datetime) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
        "joined_at": joined_at,
    }


class WorkspaceMemberRead(MemberRead):
    role: WorkspaceRole


class WorkspaceMemberList(BaseModel):
    items: list[WorkspaceMemberRead]


class WorkspaceMemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: WorkspaceRole


class OwnershipTransfer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
