"""Граница контракта модуля views."""

from datetime import datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import SortDirection, ViewGroupBy, ViewLayout, ViewScope, ViewSortBy
from app.core.schemas import reject_control_characters, reject_explicit_null
from app.modules.states.schemas import COLOR_PATTERN
from app.modules.tasks.schemas import TaskGroup
from app.modules.views.filters import FilterError, parse_filters


class FilterCondition(BaseModel):
    """Условие на одно поле. Допустимые пары поле × оператор — §4 модели данных."""

    model_config = ConfigDict(extra="forbid")

    op: str = Field(description="in, nin, eq, lt, lte, gt, gte, is_null, not_null, contains")
    value: Any = Field(
        default=None,
        description="Список id (допустим @me), тип статуса, приоритет 0–4, дата или "
        "@today, @today±Nd, @start_of_week, строка, true/false",
    )


Filters = dict[str, FilterCondition]


def filters_json(filters: Filters) -> dict[str, Any]:
    return {name: spec.model_dump(exclude_unset=True) for name, spec in filters.items()}


def _check_filters(filters: Filters | None) -> None:
    if filters is None:
        return
    try:
        parse_filters(filters_json(filters))
    except FilterError as error:
        raise ValueError(f"Фильтр {error.field}: {error.message}") from error


class ViewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    scope: ViewScope
    # Обязателен для scope = team и запрещён для остальных.
    team_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    filters: Filters = Field(default_factory=dict)
    group_by: ViewGroupBy | None = None
    sort_by: ViewSortBy = ViewSortBy.MANUAL
    sort_direction: SortDirection = SortDirection.ASC
    layout: ViewLayout = ViewLayout.LIST
    # Не указана — view встаёт последним в своём разделе меню.
    position: int | None = Field(default=None, ge=0)

    _name = field_validator("name", mode="before")(reject_control_characters)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.scope == ViewScope.TEAM) != (self.team_id is not None):
            raise ValueError("team_id указывается ровно для scope = team")
        _check_filters(self.filters)
        return self


class ViewUpdate(BaseModel):
    """Scope, команда и владелец не меняются: это другой view, а не правка этого."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    filters: Filters | None = None
    group_by: ViewGroupBy | None = None
    sort_by: ViewSortBy | None = None
    sort_direction: SortDirection | None = None
    layout: ViewLayout | None = None
    position: int | None = Field(default=None, ge=0)

    _name = field_validator("name", mode="before")(reject_control_characters)

    @model_validator(mode="after")
    def _required_stay_set(self) -> Self:
        reject_explicit_null(
            self, "name", "filters", "sort_by", "sort_direction", "layout", "position"
        )
        _check_filters(self.filters)
        return self


class ViewRead(BaseModel):
    id: UUID
    workspace_id: UUID
    scope: ViewScope
    owner_id: UUID | None
    team_id: UUID | None
    name: str
    description: str | None
    icon: str | None
    color: str | None
    filters: dict[str, Any]
    group_by: ViewGroupBy | None
    sort_by: ViewSortBy
    sort_direction: SortDirection
    layout: ViewLayout
    position: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    can_edit: bool = Field(description="Может ли текущий пользователь менять и удалять view")


class ViewList(BaseModel):
    items: list[ViewRead]


class ViewTasks(BaseModel):
    view_id: UUID
    group_by: ViewGroupBy | None
    groups: list[TaskGroup]
