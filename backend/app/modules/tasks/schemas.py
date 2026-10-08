"""Граница контракта модуля tasks.

Ссылки на задачу в теле запроса (`parent_id`, `target_id`, `after_id`, `before_id`)
принимают и UUID, и ключ `ENG-142`: агенту второе существенно удобнее.
"""

from datetime import date, datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import StateType
from app.core.pagination import Page
from app.core.schemas import reject_control_characters, reject_explicit_null

TaskRef = str
RelationView = Literal["blocks", "blocked_by", "relates_to", "duplicates", "duplicated_by"]


def _ref(**extra: Any) -> Any:
    return Field(
        min_length=1, max_length=64, description="UUID или ключ задачи, например ENG-142", **extra
    )


class TaskCreate(BaseModel):
    """Нужна команда или проект; проект сам определяет команду."""

    model_config = ConfigDict(extra="forbid")

    team_id: UUID | None = None
    project_id: UUID | None = None
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=100_000)
    # Не указан — статус команды по умолчанию.
    state_id: UUID | None = None
    assignee_id: UUID | None = None
    priority: int = Field(default=0, ge=0, le=4, description="0 — нет, 1 — срочный … 4 — низкий")
    due_date: date | None = None
    parent_id: TaskRef | None = _ref(default=None)
    label_ids: list[UUID] = Field(default_factory=list, max_length=50)

    _title = field_validator("title", mode="before")(reject_control_characters)

    @model_validator(mode="after")
    def _needs_location(self) -> Self:
        if self.team_id is None and self.project_id is None:
            raise ValueError("Нужен team_id или project_id")
        return self


class TaskUpdate(BaseModel):
    """Присланное поле меняется, отсутствующее — нет. Явный null очищает необязательное."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=100_000)
    state_id: UUID | None = None
    assignee_id: UUID | None = None
    priority: int | None = Field(default=None, ge=0, le=4)
    due_date: date | None = None
    project_id: UUID | None = None
    parent_id: TaskRef | None = _ref(default=None)

    _title = field_validator("title", mode="before")(reject_control_characters)

    @model_validator(mode="after")
    def _required_stay_set(self) -> Self:
        reject_explicit_null(self, "title", "state_id", "priority")
        return self


class TaskMove(BaseModel):
    """Перестановка и/или смена статуса одним вызовом.

    Место задаётся соседом (`after_id` / `before_id`) или краем (`position`); порядок
    общий на команду, поэтому «после X» означает «сразу после X» в любом срезе.
    """

    model_config = ConfigDict(extra="forbid")

    state_id: UUID | None = None
    after_id: TaskRef | None = _ref(default=None)
    before_id: TaskRef | None = _ref(default=None)
    position: Literal["top", "bottom"] | None = None

    @model_validator(mode="after")
    def _one_anchor(self) -> Self:
        anchors = [self.after_id, self.before_id, self.position]
        if sum(anchor is not None for anchor in anchors) > 1:
            raise ValueError("Укажите только одно из after_id, before_id, position")
        if self.state_id is None and not any(anchor is not None for anchor in anchors):
            raise ValueError("Нечего менять: нужен state_id или новое место")
        return self


class RelationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: RelationView = Field(description="Тип связи со стороны этой задачи")
    target_id: TaskRef = _ref()


class TaskLabelsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label_ids: list[UUID] = Field(max_length=50)


# --- Ответы ---------------------------------------------------------------------


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    avatar_url: str | None


class StateBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    type: StateType
    color: str


class LabelBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    color: str


class ProjectBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class TaskBrief(BaseModel):
    id: UUID
    key: str
    title: str


class RelationRead(BaseModel):
    id: UUID
    type: RelationView = Field(description="Тип связи со стороны этой задачи")
    task: TaskBrief


class TaskRead(BaseModel):
    """Плоский объект с id. Развёрнутые поля появляются только по `?expand=`."""

    id: UUID
    key: str = Field(description="Ключ задачи, например ENG-142")
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
    relations: list[RelationRead] | None = None


class TaskPage(Page[TaskRead]):
    pass


class TaskList(BaseModel):
    items: list[TaskRead]


class TaskGroup(BaseModel):
    """Группа результата view; без группировки — единственная с `key = null`."""

    key: str | None = Field(description="id, приоритет или дата; null — группа без значения")
    count: int = Field(description="Сколько задач в группе всего, а не на этой странице")
    items: list[TaskRead]
    next_cursor: str | None
    has_more: bool
