"""Модели ответов API.

Неизвестные поля игнорируются: сервер может добавить поле раньше, чем обновится SDK,
и старый клиент от этого не должен ломаться. Развёрнутые поля (`?expand=`) — `None`,
пока их не запросили.
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class Page[T](Model):
    """Страница курсорного списка."""

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


# --- Пользователь и доступ --------------------------------------------------------


class WorkspaceMembership(Model):
    workspace_id: UUID
    role: str


class TeamMembership(Model):
    team_id: UUID
    workspace_id: UUID
    role: str


class ProjectMembership(Model):
    project_id: UUID
    workspace_id: UUID
    role: str


class Memberships(Model):
    workspaces: list[WorkspaceMembership]
    teams: list[TeamMembership]
    projects: list[ProjectMembership]


class Me(Model):
    id: UUID
    email: str
    full_name: str
    avatar_url: str | None = None
    role: str
    created_at: datetime
    auth_method: str
    scopes: list[str]
    memberships: Memberships


class Notification(Model):
    id: UUID
    workspace_id: UUID
    type: str
    task_id: UUID | None
    comment_id: UUID | None
    actor_id: UUID
    read_at: datetime | None
    created_at: datetime


# --- Организация ------------------------------------------------------------------


class Workspace(Model):
    id: UUID
    name: str
    slug: str
    avatar_url: str | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class Member(Model):
    """Участник workspace, команды или проекта; `role` — роль на этом уровне."""

    user_id: UUID
    email: str
    full_name: str
    avatar_url: str | None = None
    joined_at: datetime
    role: str


class Team(Model):
    id: UUID
    workspace_id: UUID
    key: str
    name: str
    description: str | None = None
    is_private: bool
    created_at: datetime
    updated_at: datetime


class Project(Model):
    id: UUID
    workspace_id: UUID
    team_id: UUID
    name: str
    description: str | None = None
    status: str
    lead_id: UUID | None = None
    start_date: date | None = None
    target_date: date | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class Invitation(Model):
    id: UUID
    workspace_id: UUID
    email: str
    scope_type: str
    scope_id: UUID
    role: str
    status: str
    invited_by: UUID
    expires_at: datetime
    created_at: datetime


class State(Model):
    id: UUID
    workspace_id: UUID
    team_id: UUID
    name: str
    type: str
    color: str
    position: int
    is_default: bool
    created_at: datetime


class Label(Model):
    id: UUID
    workspace_id: UUID
    team_id: UUID | None
    name: str
    color: str
    created_at: datetime


# --- Задачи -----------------------------------------------------------------------


class UserBrief(Model):
    id: UUID
    email: str
    full_name: str
    avatar_url: str | None = None


class StateBrief(Model):
    id: UUID
    name: str
    type: str
    color: str


class LabelBrief(Model):
    id: UUID
    name: str
    color: str


class ProjectBrief(Model):
    id: UUID
    name: str


class TaskBrief(Model):
    id: UUID
    key: str
    title: str


class Relation(Model):
    id: UUID
    type: str
    task: TaskBrief


class Task(Model):
    id: UUID
    key: str
    workspace_id: UUID
    team_id: UUID
    project_id: UUID | None
    number: int
    title: str
    description: str | None
    state_id: UUID
    assignee_id: UUID | None
    creator_id: UUID
    priority: int
    due_date: date | None
    parent_id: UUID | None
    label_ids: list[UUID]
    sort_order: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    assignee: UserBrief | None = None
    creator: UserBrief | None = None
    state: StateBrief | None = None
    labels: list[LabelBrief] | None = None
    project: ProjectBrief | None = None
    parent: TaskBrief | None = None
    relations: list[Relation] | None = None


class Comment(Model):
    id: UUID
    task_id: UUID
    author_id: UUID
    author_token_id: UUID | None
    parent_id: UUID | None
    body: str
    mention_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


class Activity(Model):
    id: UUID
    task_id: UUID | None
    actor_id: UUID
    actor_token_id: UUID | None
    type: str
    payload: dict[str, Any]
    created_at: datetime


# --- Views ------------------------------------------------------------------------


class View(Model):
    id: UUID
    workspace_id: UUID
    scope: str
    owner_id: UUID | None
    team_id: UUID | None
    name: str
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    filters: dict[str, Any]
    group_by: str | None
    sort_by: str
    sort_direction: str
    layout: str
    position: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    can_edit: bool


class TaskGroup(Model):
    """Группа результата view; без группировки — единственная с `key = None`."""

    key: str | None
    count: int
    items: list[Task]
    next_cursor: str | None
    has_more: bool


class ViewResult(Model):
    group_by: str | None
    groups: list[TaskGroup]
