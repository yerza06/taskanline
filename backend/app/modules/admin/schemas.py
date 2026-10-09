"""Граница контракта раздела администрирования.

Ни одна схема здесь не несёт содержимого рабочих пространств: ни заголовков задач,
ни описаний проектов, ни текстов комментариев (админ-спека §2). Названия и slug
пространств — можно: без них администратор не найдёт брошенное.
"""

from datetime import date, datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import (
    AuditAction,
    AuditTarget,
    InstanceRole,
    LoginKind,
    RegistrationMode,
    TokenScope,
    WorkspaceRole,
)
from app.core.pagination import Page
from app.core.schemas import reject_control_characters, reject_explicit_null


class ReauthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=128)


class AdminSession(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    role: InstanceRole
    reauth_until: datetime | None = Field(
        description="До какого момента действует подтверждение паролем; null — не подтверждено"
    )


# --- Дашборд ------------------------------------------------------------------------


class UserCounts(BaseModel):
    total: int
    active: int
    blocked: int
    deleted: int


class Stats(BaseModel):
    users: UserCounts
    workspaces: int
    teams: int
    tasks: int
    version: str
    migration: str | None = Field(description="Текущая ревизия базы")
    migration_head: str | None = Field(description="Последняя ревизия в коде")


# --- Пользователи -------------------------------------------------------------------

UserStatus = str  # active | blocked | deleted


class AdminUserRow(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: InstanceRole
    status: str = Field(description="active, blocked или deleted")
    created_at: datetime
    last_seen_at: datetime | None


class AdminUserPage(Page[AdminUserRow]):
    pass


class AdminMembership(BaseModel):
    workspace_id: UUID
    workspace_name: str
    workspace_slug: str
    role: WorkspaceRole


class AdminToken(BaseModel):
    id: UUID
    name: str
    prefix: str
    scope: TokenScope
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None


class AdminLogin(BaseModel):
    kind: LoginKind
    ip: str | None
    user_agent: str | None
    created_at: datetime


class AdminUserDetail(AdminUserRow):
    memberships: list[AdminMembership]
    tokens: list[AdminToken]
    logins: list[AdminLogin] = Field(description="Последние 20 входов")


class RoleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: InstanceRole


class OwnerOfWorkspace(BaseModel):
    id: UUID
    name: str
    slug: str


# --- Рабочие пространства -----------------------------------------------------------


class AdminOwner(BaseModel):
    user_id: UUID
    email: str


class AdminWorkspaceRow(BaseModel):
    id: UUID
    name: str
    slug: str
    owners: list[AdminOwner]
    members: int
    teams: int
    tasks: int
    created_at: datetime
    last_activity_at: datetime | None


class AdminWorkspacePage(Page[AdminWorkspaceRow]):
    pass


class AdminWorkspaceMember(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    role: WorkspaceRole


class AdminWorkspaceDetail(AdminWorkspaceRow):
    member_list: list[AdminWorkspaceMember]


# --- Настройки ----------------------------------------------------------------------


class SettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instance_name: str
    registration_mode: RegistrationMode
    allowed_email_domains: list[str]
    invitation_ttl_days: int
    maintenance_mode: bool
    updated_by: UUID | None
    updated_at: datetime


DOMAIN_PATTERN = r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"


class SettingsUpdate(BaseModel):
    """Переданное поле меняется, отсутствующее — нет. Явный null запрещён: у каждого
    параметра есть значение."""

    model_config = ConfigDict(extra="forbid")

    instance_name: str | None = Field(default=None, min_length=1, max_length=100)
    registration_mode: RegistrationMode | None = None
    allowed_email_domains: list[str] | None = Field(default=None, max_length=100)
    invitation_ttl_days: int | None = Field(default=None, ge=1, le=365)
    maintenance_mode: bool | None = None

    _name = field_validator("instance_name", mode="before")(reject_control_characters)

    @field_validator("allowed_email_domains")
    @classmethod
    def _domains(cls, value: list[str] | None) -> list[str] | None:
        import re

        if value is None:
            return None
        cleaned = sorted({item.strip().lower().lstrip("@") for item in value if item.strip()})
        bad = [item for item in cleaned if not re.match(DOMAIN_PATTERN, item)]
        if bad:
            raise ValueError(f"Не домен: {', '.join(bad)}")
        return cleaned

    @model_validator(mode="after")
    def _required_stay_set(self) -> Self:
        reject_explicit_null(
            self,
            "instance_name",
            "registration_mode",
            "allowed_email_domains",
            "invitation_ttl_days",
            "maintenance_mode",
        )
        return self


# --- Журнал аудита ------------------------------------------------------------------


class AuditActor(BaseModel):
    id: UUID
    email: str
    full_name: str


class AuditEntry(BaseModel):
    id: UUID
    actor: AuditActor
    action: AuditAction
    target_type: AuditTarget | None
    target_id: UUID | None
    payload: dict[str, Any]
    ip: str | None
    user_agent: str | None
    created_at: datetime


class AuditPage(Page[AuditEntry]):
    pass


class AuditFilters(BaseModel):
    actor_id: UUID | None = None
    action: AuditAction | None = None
    target_type: AuditTarget | None = None
    target_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
