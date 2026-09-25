"""Граница контракта модуля invitations."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.enums import InvitationScope, InvitationStatus
from app.modules.users.schemas import normalize_email

# Та же таблица, что CHECK role_matches_scope в базе. `owner` не приглашается —
# владение только передаётся.
ALLOWED_ROLES: dict[InvitationScope, frozenset[str]] = {
    InvitationScope.WORKSPACE: frozenset({"admin", "member", "guest"}),
    InvitationScope.TEAM: frozenset({"lead", "member"}),
    InvitationScope.PROJECT: frozenset({"admin", "member", "viewer"}),
}


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    scope_type: InvitationScope
    scope_id: UUID
    role: str = Field(max_length=16)

    _normalize = field_validator("email")(normalize_email)

    @model_validator(mode="after")
    def _role_exists_on_level(self) -> Self:
        if self.role not in ALLOWED_ROLES[self.scope_type]:
            raise ValueError(f"Роль {self.role} недоступна на уровне {self.scope_type}")
        return self


class InvitationRead(BaseModel):
    """Приглашение для того, кто им управляет. Токена здесь нет и быть не может."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    email: str
    scope_type: InvitationScope
    scope_id: UUID
    role: str
    status: InvitationStatus
    invited_by: UUID
    expires_at: datetime
    created_at: datetime


class InvitationList(BaseModel):
    items: list[InvitationRead]


class InvitationPreview(BaseModel):
    """Публичное превью по токену: ни участников, ни задач — токен мог попасть не туда."""

    workspace_name: str
    inviter_name: str
    email: str
    scope_type: InvitationScope
    role: str
    status: InvitationStatus
    expires_at: datetime


class InvitationAccept(BaseModel):
    """Тело принятия без сессии: учётная запись заводится на адрес из приглашения."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class InvitationAccepted(BaseModel):
    workspace_id: UUID
    scope_type: InvitationScope
    scope_id: UUID
    role: str
