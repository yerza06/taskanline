"""Граница контракта модуля users."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.enums import AuthMethod, InstanceRole, ProjectRole, TeamRole, WorkspaceRole


def normalize_email(value: str) -> str:
    """Email хранится в нижнем регистре; CITEXT в базе — вторая линия обороны."""
    return value.strip().lower()


class UserRead(BaseModel):
    """Публичный вид пользователя. Хеша пароля здесь нет и быть не может."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    avatar_url: str | None
    role: InstanceRole
    created_at: datetime


class UserUpdate(BaseModel):
    """Что человек меняет в своём профиле.

    `extra="forbid"`: попытка прислать `role` или `email` должна отвечать 422, а не
    молча игнорироваться — иначе клиент будет думать, что изменение прошло.
    """

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=2000)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)

    _normalize = field_validator("email")(normalize_email)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    _normalize = field_validator("email")(normalize_email)


class WorkspaceMembership(BaseModel):
    workspace_id: UUID
    role: WorkspaceRole


class TeamMembership(BaseModel):
    team_id: UUID
    workspace_id: UUID
    role: TeamRole


class ProjectMembership(BaseModel):
    project_id: UUID
    workspace_id: UUID
    role: ProjectRole


class Memberships(BaseModel):
    """Где человек числится — плоско, одними идентификаторами (§3.6)."""

    workspaces: list[WorkspaceMembership]
    teams: list[TeamMembership]
    projects: list[ProjectMembership]


class MeResponse(UserRead):
    """Профиль плюс то, чем именно доказана личность.

    Клиенту важно знать свой scope: интерфейс агента по нему решает, показывать
    ли кнопки изменения.
    """

    auth_method: AuthMethod
    scopes: list[str]
    memberships: Memberships
