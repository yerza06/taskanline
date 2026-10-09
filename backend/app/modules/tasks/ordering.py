"""Сортировка и группировка задач для выполнения view.

Сортировка — составной ключ `(выражение, id)`: `id` разрывает равенства, и курсор по
тому же ключу даёт стабильный обход. Пустые значения стоят последними в обе стороны
направления — поэтому выражения подставляют вместо NULL «край» в нужную сторону, а не
полагаются на `NULLS LAST`, который ключ курсора не выразил бы.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, case, func, literal, tuple_

from app.core.enums import SortDirection, ViewGroupBy, ViewSortBy
from app.core.errors import ApiError
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.labels.models import TaskLabel
from app.modules.tasks.models import Task

# «Без приоритета» (0) — после «низкого» (4).
NO_PRIORITY_RANK = 5
_LAST_DAY, _FIRST_DAY = date(9999, 12, 31), date(1, 1, 1)


def _invalid_cursor() -> ApiError:
    return ApiError(400, "invalid_cursor", "Курсор повреждён или устарел")


@dataclass(frozen=True)
class SortSpec:
    by: ViewSortBy
    direction: SortDirection

    @property
    def descending(self) -> bool:
        return self.direction == SortDirection.DESC

    def expression(self) -> Any:
        match self.by:
            case ViewSortBy.MANUAL:
                return Task.sort_order
            case ViewSortBy.PRIORITY:
                return case((Task.priority == 0, NO_PRIORITY_RANK), else_=Task.priority)
            case ViewSortBy.DUE_DATE:
                edge = _FIRST_DAY if self.descending else _LAST_DAY
                return func.coalesce(Task.due_date, edge)
            case ViewSortBy.CREATED_AT:
                return Task.created_at
            case ViewSortBy.UPDATED_AT:
                return Task.updated_at
            case ViewSortBy.TITLE:
                return Task.title
        raise AssertionError(self.by)

    def order_by(self) -> list[Any]:
        if self.descending:
            return [self.expression().desc(), Task.id.desc()]
        return [self.expression(), Task.id]

    def after(self, position: tuple[Any, UUID]) -> ColumnElement[bool]:
        """Строго после позиции курсора в направлении сортировки."""
        current = tuple_(self.expression(), Task.id)
        bound = tuple_(*map(literal, position))
        return current < bound if self.descending else current > bound

    def value_of(self, task: Task) -> Any:
        """Значение ключа задачи — то же, что считает `expression()` в базе."""
        match self.by:
            case ViewSortBy.MANUAL:
                return task.sort_order
            case ViewSortBy.PRIORITY:
                return task.priority or NO_PRIORITY_RANK
            case ViewSortBy.DUE_DATE:
                return task.due_date or (_FIRST_DAY if self.descending else _LAST_DAY)
            case ViewSortBy.CREATED_AT:
                return task.created_at
            case ViewSortBy.UPDATED_AT:
                return task.updated_at
            case ViewSortBy.TITLE:
                return task.title
        raise AssertionError(self.by)

    def encode(self, task: Task) -> str:
        value = self.value_of(task)
        raw = value.isoformat() if isinstance(value, date) else value
        # Поле сортировки в курсоре: сменили сортировку view — старый курсор отвергается.
        return encode_cursor(f"{self.by}:{self.direction}", raw, task.id)

    def decode(self, cursor: str) -> tuple[Any, UUID]:
        sort, raw, task_id = decode_cursor(cursor, 3)
        if sort != f"{self.by}:{self.direction}":
            raise _invalid_cursor()
        try:
            value: Any
            match self.by:
                case ViewSortBy.PRIORITY:
                    value = int(raw)
                case ViewSortBy.DUE_DATE:
                    value = date.fromisoformat(raw)
                case ViewSortBy.CREATED_AT | ViewSortBy.UPDATED_AT:
                    value = datetime.fromisoformat(raw)
                case _:
                    value = raw
            return value, UUID(task_id)
        except ValueError as error:
            raise _invalid_cursor() from error


def group_expression(group_by: ViewGroupBy) -> Any:
    """Ключ группы. Для меток — колонка присоединённой `task_labels`."""
    match group_by:
        case ViewGroupBy.STATE:
            return Task.state_id
        case ViewGroupBy.ASSIGNEE:
            return Task.assignee_id
        case ViewGroupBy.PRIORITY:
            return Task.priority
        case ViewGroupBy.PROJECT:
            return Task.project_id
        case ViewGroupBy.DUE_DATE:
            return Task.due_date
        case ViewGroupBy.LABEL:
            return TaskLabel.label_id
    raise AssertionError(group_by)


NO_GROUP = "none"


def parse_group_key(group_by: ViewGroupBy, raw: str) -> Any:
    """Ключ группы из `?group=` → значение колонки; `none` — группа без значения."""
    if raw == NO_GROUP:
        return None
    try:
        match group_by:
            case ViewGroupBy.PRIORITY:
                value = int(raw)
                if not 0 <= value <= 4:
                    raise ValueError(raw)
                return value
            case ViewGroupBy.DUE_DATE:
                return date.fromisoformat(raw)
            case _:
                return UUID(raw)
    except ValueError:
        raise ApiError(
            400, "invalid_group", "Неизвестная группа", {"group": raw, "group_by": group_by}
        ) from None


def format_group_key(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else str(value)
