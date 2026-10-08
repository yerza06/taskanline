"""Грамматика фильтров view и их трансляция в SQL (§4 модели данных).

`filters` — плоский объект: ключ — поле, значение — `{"op", "value"}`. Условия
соединяются только через AND; список значений внутри поля означает OR.

Трансляция идёт по белому списку: каждое поле отображается в заранее написанное
выражение SQLAlchemy, а значения всегда уходят параметрами. Ни одно имя поля, ни один
оператор и ни одно значение из запроса не попадает в текст SQL.

Проверка — дважды: при сохранении view (422 — в базу не попадает мусор) и при
выполнении (`400 invalid_filter` — переименование поля в будущем не уронит старые
view, а вернёт внятную ошибку).
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, not_, or_, select
from sqlalchemy.orm import aliased

from app.core.enums import CLOSED_STATE_TYPES, RelationType, StateType
from app.modules.labels.models import TaskLabel
from app.modules.states.models import WorkflowState
from app.modules.tasks.models import Task, TaskRelation


class FilterField(StrEnum):
    TEAM_ID = "team_id"
    PROJECT_ID = "project_id"
    STATE_ID = "state_id"
    STATE_TYPE = "state_type"
    ASSIGNEE_ID = "assignee_id"
    CREATOR_ID = "creator_id"
    LABEL_ID = "label_id"
    PRIORITY = "priority"
    DUE_DATE = "due_date"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    COMPLETED_AT = "completed_at"
    TITLE = "title"
    HAS_PARENT = "has_parent"
    IS_BLOCKED = "is_blocked"


class FilterOp(StrEnum):
    IN = "in"
    NIN = "nin"
    EQ = "eq"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    IS_NULL = "is_null"
    NOT_NULL = "not_null"
    CONTAINS = "contains"


ID_FIELDS = frozenset(
    {
        FilterField.TEAM_ID,
        FilterField.PROJECT_ID,
        FilterField.STATE_ID,
        FilterField.ASSIGNEE_ID,
        FilterField.CREATOR_ID,
        FilterField.LABEL_ID,
    }
)
DATE_FIELDS = frozenset(
    {FilterField.DUE_DATE, FilterField.CREATED_AT, FilterField.UPDATED_AT, FilterField.COMPLETED_AT}
)
COMPARISONS = frozenset({FilterOp.EQ, FilterOp.LT, FilterOp.LTE, FilterOp.GT, FilterOp.GTE})
# `@me` осмыслен только там, где значение — человек.
PERSON_FIELDS = frozenset({FilterField.ASSIGNEE_ID, FilterField.CREATOR_ID})

ALLOWED_OPS: dict[FilterField, frozenset[FilterOp]] = {
    **{
        field: frozenset({FilterOp.IN, FilterOp.NIN})
        for field in ID_FIELDS | {FilterField.STATE_TYPE}
    },
    FilterField.PRIORITY: COMPARISONS | {FilterOp.IN},
    **{field: COMPARISONS | {FilterOp.IS_NULL, FilterOp.NOT_NULL} for field in DATE_FIELDS},
    FilterField.TITLE: frozenset({FilterOp.CONTAINS}),
    FilterField.HAS_PARENT: frozenset({FilterOp.EQ}),
    FilterField.IS_BLOCKED: frozenset({FilterOp.EQ}),
}

ME = "@me"
MAX_VALUES = 100
MAX_TEXT = 200
DATE_EXPRESSION = re.compile(r"^@today(?:([+-])(\d{1,4})d)?$")


class FilterError(ValueError):
    """Фильтр не по грамматике. `field` — где именно, для `details` ответа."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


@dataclass(frozen=True)
class Condition:
    """Проверенное условие; значение уже приведено к своему типу."""

    field: FilterField
    op: FilterOp
    value: Any


@dataclass(frozen=True)
class FilterContext:
    """Чем разрешаются динамические значения — в момент выполнения, а не сохранения."""

    user_id: UUID
    today: date


def parse_filters(raw: Any) -> list[Condition]:
    """Сырой JSON → список условий. Любое нарушение — `FilterError`."""
    if not isinstance(raw, dict):
        raise FilterError("filters", "ожидался объект {поле: {op, value}}")
    conditions = []
    for name, spec in raw.items():
        try:
            field = FilterField(name)
        except ValueError:
            raise FilterError(str(name), "неизвестное поле") from None
        if not isinstance(spec, dict) or "op" not in spec or set(spec) - {"op", "value"}:
            raise FilterError(field, "ожидался объект {op, value}")
        try:
            op = FilterOp(spec["op"])
        except ValueError:
            raise FilterError(field, f"неизвестный оператор {spec['op']!r}") from None
        if op not in ALLOWED_OPS[field]:
            allowed = ", ".join(sorted(ALLOWED_OPS[field]))
            raise FilterError(field, f"оператор {op} недопустим, можно: {allowed}")
        conditions.append(Condition(field, op, _value(field, op, spec.get("value"))))
    return conditions


def _value(field: FilterField, op: FilterOp, value: Any) -> Any:
    if field in ID_FIELDS:
        return [_id(field, item) for item in _list(field, value)]
    if field == FilterField.STATE_TYPE:
        try:
            return [StateType(item) for item in _list(field, value)]
        except ValueError:
            raise FilterError(field, "неизвестный тип статуса") from None
    if field == FilterField.PRIORITY:
        if op == FilterOp.IN:
            return [_priority(field, item) for item in _list(field, value)]
        return _priority(field, value)
    if field in DATE_FIELDS:
        if op in (FilterOp.IS_NULL, FilterOp.NOT_NULL):
            if value is not None:
                raise FilterError(field, f"оператор {op} не принимает значения")
            return None
        if not isinstance(value, str):
            raise FilterError(field, "ожидалась дата YYYY-MM-DD или @today±Nd, @start_of_week")
        resolve_date(value, date.today(), field=field)  # проверка формы; дата — при выполнении
        return value
    if field == FilterField.TITLE:
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
            raise FilterError(field, f"ожидалась непустая строка до {MAX_TEXT} символов")
        return value
    # has_parent, is_blocked
    if not isinstance(value, bool):
        raise FilterError(field, "ожидалось true или false")
    return value


def _list(field: FilterField, value: Any) -> list[Any]:
    if not isinstance(value, list) or not value or len(value) > MAX_VALUES:
        raise FilterError(field, f"ожидался непустой список до {MAX_VALUES} значений")
    return value


def _id(field: FilterField, item: Any) -> UUID | str:
    if item == ME:
        if field not in PERSON_FIELDS:
            raise FilterError(field, "@me допустим только в assignee_id и creator_id")
        return ME
    try:
        return UUID(str(item))
    except ValueError:
        raise FilterError(field, f"ожидался UUID, получено {item!r}") from None


def _priority(field: FilterField, value: Any) -> int:
    # bool — подкласс int в Python: true не должен стать приоритетом 1.
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 4:
        raise FilterError(field, "приоритет — целое от 0 до 4")
    return value


def resolve_date(value: str, today: date, *, field: str = "date") -> date:
    """`@today`, `@today+7d`, `@today-3d`, `@start_of_week` (понедельник) или ISO-дата."""
    if value == "@start_of_week":
        return today - timedelta(days=today.weekday())
    match = DATE_EXPRESSION.match(value)
    if match:
        sign, days = match.groups()
        shift = timedelta(days=int(days)) if days else timedelta()
        return today - shift if sign == "-" else today + shift
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise FilterError(field, f"не дата: {value!r}") from None


# --- Трансляция ------------------------------------------------------------------


def translate(conditions: list[Condition], ctx: FilterContext) -> list[ColumnElement[bool]]:
    """Условия → выражения SQLAlchemy над `tasks`. Значения — только параметрами."""
    return [_translate(condition, ctx) for condition in conditions]


_COLUMNS = {
    FilterField.TEAM_ID: Task.team_id,
    FilterField.PROJECT_ID: Task.project_id,
    FilterField.STATE_ID: Task.state_id,
    FilterField.ASSIGNEE_ID: Task.assignee_id,
    FilterField.CREATOR_ID: Task.creator_id,
    FilterField.DUE_DATE: Task.due_date,
    FilterField.CREATED_AT: Task.created_at,
    FilterField.UPDATED_AT: Task.updated_at,
    FilterField.COMPLETED_AT: Task.completed_at,
}
# Необязательные поля: «не равно X» включает задачи, где значения нет вовсе.
_NULLABLE = frozenset({FilterField.PROJECT_ID, FilterField.ASSIGNEE_ID})


def _translate(condition: Condition, ctx: FilterContext) -> ColumnElement[bool]:
    field, op, value = condition.field, condition.op, condition.value

    if field == FilterField.LABEL_ID:
        labelled = exists().where(TaskLabel.task_id == Task.id, TaskLabel.label_id.in_(value))
        return labelled if op == FilterOp.IN else not_(labelled)

    if field == FilterField.STATE_TYPE:
        states = select(WorkflowState.id).where(WorkflowState.type.in_(value))
        return Task.state_id.in_(states) if op == FilterOp.IN else Task.state_id.not_in(states)

    if field in ID_FIELDS:
        column = _COLUMNS[field]
        ids = [ctx.user_id if item == ME else item for item in value]
        if op == FilterOp.IN:
            return column.in_(ids)
        if field in _NULLABLE:
            return or_(column.is_(None), column.not_in(ids))
        return column.not_in(ids)

    if field == FilterField.PRIORITY:
        if op == FilterOp.IN:
            return Task.priority.in_(value)
        if op == FilterOp.EQ:
            return _compare(Task.priority, op, value)
        # Сравнения — среди назначенных приоритетов: 0 значит «нет приоритета», а не
        # «важнее срочного», и в «приоритет не ниже высокого» попадать не должен.
        return and_(Task.priority > 0, _compare(Task.priority, op, value))

    if field in DATE_FIELDS:
        column = _COLUMNS[field]
        if op == FilterOp.IS_NULL:
            return column.is_(None)
        if op == FilterOp.NOT_NULL:
            return column.is_not(None)
        day = resolve_date(value, ctx.today, field=field)
        if field == FilterField.DUE_DATE:
            return _compare(column, op, day)
        return _day_bounds(column, op, day)

    if field == FilterField.TITLE:
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return Task.title.ilike(f"%{escaped}%", escape="\\")

    if field == FilterField.HAS_PARENT:
        return Task.parent_id.is_not(None) if value else Task.parent_id.is_(None)

    if field == FilterField.IS_BLOCKED:
        blocked = _is_blocked()
        return blocked if value else not_(blocked)

    raise AssertionError(field)  # pragma: no cover — белый список исчерпан выше


def _compare(column: Any, op: FilterOp, value: Any) -> ColumnElement[bool]:
    match op:
        case FilterOp.EQ:
            return column == value  # type: ignore[no-any-return]
        case FilterOp.LT:
            return column < value  # type: ignore[no-any-return]
        case FilterOp.LTE:
            return column <= value  # type: ignore[no-any-return]
        case FilterOp.GT:
            return column > value  # type: ignore[no-any-return]
        case FilterOp.GTE:
            return column >= value  # type: ignore[no-any-return]
    raise AssertionError(op)


def _day_bounds(column: Any, op: FilterOp, day: date) -> ColumnElement[bool]:
    """Метка времени против дня (UTC): «lte сегодня» — до конца сегодняшнего дня."""
    start = datetime.combine(day, time.min, tzinfo=UTC)
    end = start + timedelta(days=1)
    match op:
        case FilterOp.EQ:
            return and_(column >= start, column < end)
        case FilterOp.LT:
            return column < start  # type: ignore[no-any-return]
        case FilterOp.LTE:
            return column < end  # type: ignore[no-any-return]
        case FilterOp.GT:
            return column >= end  # type: ignore[no-any-return]
        case FilterOp.GTE:
            return column >= start  # type: ignore[no-any-return]
    raise AssertionError(op)


def _is_blocked() -> ColumnElement[bool]:
    """Есть незакрытая неудалённая задача, которая блокирует эту."""
    blocker = aliased(Task)
    closed = select(WorkflowState.id).where(WorkflowState.type.in_(CLOSED_STATE_TYPES))
    return exists().where(
        TaskRelation.target_task_id == Task.id,
        TaskRelation.type == RelationType.BLOCKS,
        blocker.id == TaskRelation.source_task_id,
        blocker.deleted_at.is_(None),
        blocker.state_id.not_in(closed),
    )
