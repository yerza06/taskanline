"""Граница контракта модуля projects."""

from datetime import date, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import ProjectRole, ProjectStatus
from app.core.schemas import reject_explicit_null
from app.modules.workspaces.schemas import MemberRead


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20000)
    status: ProjectStatus = ProjectStatus.PLANNED
    lead_id: UUID | None = None
    start_date: date | None = None
    target_date: date | None = None


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20000)
    status: ProjectStatus | None = None
    lead_id: UUID | None = None
    start_date: date | None = None
    target_date: date | None = None

    @model_validator(mode="after")
    def _required_stay_set(self) -> Self:
        reject_explicit_null(self, "name", "status")
        return self


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    team_id: UUID
    name: str
    description: str | None
    status: ProjectStatus
    lead_id: UUID | None
    start_date: date | None
    target_date: date | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProjectList(BaseModel):
    items: list[ProjectRead]


class ProjectMemberRead(MemberRead):
    role: ProjectRole


class ProjectMemberList(BaseModel):
    items: list[ProjectMemberRead]


class ProjectMemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ProjectRole
