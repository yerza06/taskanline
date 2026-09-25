"""Перечисления, дублирующие ограничения `CHECK` в базе.

В схеме это `VARCHAR` с `CHECK`, а не нативный enum PostgreSQL: добавление значения
в нативный enum — миграция с блокировкой, правка `CHECK` — нет. Расплата за это —
список значений в двух местах, и здесь его питоновская половина.
"""

from enum import StrEnum


class InstanceRole(StrEnum):
    """Роль на уровне сервера — ось, независимая от ролей внутри workspace."""

    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    SUPPORT = "support"
    USER = "user"


class TokenScope(StrEnum):
    """Что разрешено токену агента."""

    READ = "read"
    READ_WRITE = "read_write"


class AuthMethod(StrEnum):
    """Чем доказана личность: cookie-сессией человека или токеном агента."""

    SESSION = "session"
    TOKEN = "token"


class WorkspaceRole(StrEnum):
    """Роль участника внутри рабочего пространства."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    GUEST = "guest"


class TeamRole(StrEnum):
    """Роль участника внутри команды."""

    LEAD = "lead"
    MEMBER = "member"


class ProjectRole(StrEnum):
    """Роль участника внутри проекта."""

    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class ProjectStatus(StrEnum):
    """Статус проекта."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELED = "canceled"


class InvitationScope(StrEnum):
    """Уровень, на который зовут. Значения совпадают с `AccessTarget` в permissions."""

    WORKSPACE = "workspace"
    TEAM = "team"
    PROJECT = "project"


class InvitationStatus(StrEnum):
    """Статус приглашения."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"
