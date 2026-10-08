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


class StateType(StrEnum):
    """Тип workflow-статуса: по нему, а не по названию, работают фильтры и отчёты."""

    BACKLOG = "backlog"
    UNSTARTED = "unstarted"
    STARTED = "started"
    COMPLETED = "completed"
    CANCELED = "canceled"


# Статусы, переход в которые закрывает задачу и ставит `completed_at`.
CLOSED_STATE_TYPES = frozenset({StateType.COMPLETED, StateType.CANCELED})


class RelationType(StrEnum):
    """Хранимый тип связи. `blocked_by` и `duplicated_by` — те же строки с другого конца."""

    BLOCKS = "blocks"
    RELATES_TO = "relates_to"
    DUPLICATES = "duplicates"


class ActivityType(StrEnum):
    """Событие в истории задачи."""

    TASK_CREATED = "task_created"
    TITLE_CHANGED = "title_changed"
    DESCRIPTION_CHANGED = "description_changed"
    STATE_CHANGED = "state_changed"
    ASSIGNEE_CHANGED = "assignee_changed"
    PRIORITY_CHANGED = "priority_changed"
    DUE_DATE_CHANGED = "due_date_changed"
    PROJECT_CHANGED = "project_changed"
    PARENT_CHANGED = "parent_changed"
    LABEL_ADDED = "label_added"
    LABEL_REMOVED = "label_removed"
    RELATION_ADDED = "relation_added"
    RELATION_REMOVED = "relation_removed"
    COMMENTED = "commented"
    TASK_MOVED = "task_moved"
    TASK_DELETED = "task_deleted"
    TASK_RESTORED = "task_restored"


class NotificationType(StrEnum):
    """Повод уведомления. На этапе 3 создаются только `mentioned` и `assigned`."""

    MENTIONED = "mentioned"
    ASSIGNED = "assigned"
    COMMENTED = "commented"
    STATE_CHANGED = "state_changed"
