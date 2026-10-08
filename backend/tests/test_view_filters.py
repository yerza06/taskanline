"""Грамматика фильтров view и транслятор в SQL: каждое поле и оператор → ожидаемый SQL.

SQL сравнивается в том виде, в каком его компилирует диалект PostgreSQL, — значения
стоят плейсхолдерами (`%(…)s`, `__[POSTCOMPILE_…]`) и проверяются отдельно в `params`.
Это и есть гарантия «только параметризованные значения».
"""

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.core.enums import StateType
from app.modules.tasks.models import Task
from app.modules.views.filters import (
    FilterContext,
    FilterError,
    parse_filters,
    resolve_date,
    translate,
)

ID = "019a5c1e-0000-7000-8000-000000000001"
ME_ID = UUID("019a5c1e-0000-7000-8000-0000000000ff")
# Четверг: неделя началась в понедельник 5 октября.
TODAY = date(2026, 10, 8)
CTX = FilterContext(user_id=ME_ID, today=TODAY)
DIALECT = postgresql.dialect()  # type: ignore[no-untyped-call]


def compiled(filters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """WHERE-часть запроса по задачам и её параметры."""
    stmt = select(Task.id).where(*translate(parse_filters(filters), CTX))
    result = stmt.compile(dialect=DIALECT)
    return " ".join(str(result).split("WHERE", 1)[1].split()), result.params


def midnight(day: int) -> datetime:
    return datetime(2026, 10, day, tzinfo=UTC)


CASES: list[tuple[str, str, Any, str, dict[str, Any]]] = [
    ("team_id", "in", [ID], "tasks.team_id IN (__[POSTCOMPILE_team_id_1])",
     {"team_id_1": [UUID(ID)]}),
    ("team_id", "nin", [ID], "(tasks.team_id NOT IN (__[POSTCOMPILE_team_id_1]))",
     {"team_id_1": [UUID(ID)]}),
    ("project_id", "in", [ID], "tasks.project_id IN (__[POSTCOMPILE_project_id_1])",
     {"project_id_1": [UUID(ID)]}),
    ("project_id", "nin", [ID],
     "tasks.project_id IS NULL OR (tasks.project_id NOT IN (__[POSTCOMPILE_project_id_1]))",
     {"project_id_1": [UUID(ID)]}),
    ("state_id", "in", [ID], "tasks.state_id IN (__[POSTCOMPILE_state_id_1])",
     {"state_id_1": [UUID(ID)]}),
    ("state_id", "nin", [ID], "(tasks.state_id NOT IN (__[POSTCOMPILE_state_id_1]))",
     {"state_id_1": [UUID(ID)]}),
    ("state_type", "in", ["started"],
     "tasks.state_id IN (SELECT workflow_states.id FROM workflow_states"
     " WHERE workflow_states.type IN (__[POSTCOMPILE_type_1]))",
     {"type_1": [StateType.STARTED]}),
    ("state_type", "nin", ["completed", "canceled"],
     "(tasks.state_id NOT IN (SELECT workflow_states.id FROM workflow_states"
     " WHERE workflow_states.type IN (__[POSTCOMPILE_type_1])))",
     {"type_1": [StateType.COMPLETED, StateType.CANCELED]}),
    ("assignee_id", "in", ["@me", ID], "tasks.assignee_id IN (__[POSTCOMPILE_assignee_id_1])",
     {"assignee_id_1": [ME_ID, UUID(ID)]}),
    ("assignee_id", "nin", ["@me"],
     "tasks.assignee_id IS NULL OR (tasks.assignee_id NOT IN (__[POSTCOMPILE_assignee_id_1]))",
     {"assignee_id_1": [ME_ID]}),
    ("creator_id", "in", ["@me"], "tasks.creator_id IN (__[POSTCOMPILE_creator_id_1])",
     {"creator_id_1": [ME_ID]}),
    ("creator_id", "nin", [ID], "(tasks.creator_id NOT IN (__[POSTCOMPILE_creator_id_1]))",
     {"creator_id_1": [UUID(ID)]}),
    ("label_id", "in", [ID],
     "EXISTS (SELECT * FROM task_labels WHERE task_labels.task_id = tasks.id"
     " AND task_labels.label_id IN (__[POSTCOMPILE_label_id_1]))",
     {"label_id_1": [UUID(ID)]}),
    ("label_id", "nin", [ID],
     "NOT (EXISTS (SELECT * FROM task_labels WHERE task_labels.task_id = tasks.id"
     " AND task_labels.label_id IN (__[POSTCOMPILE_label_id_1])))",
     {"label_id_1": [UUID(ID)]}),
    ("priority", "eq", 0, "tasks.priority = %(priority_1)s", {"priority_1": 0}),
    ("priority", "lt", 3, "tasks.priority > %(priority_1)s AND tasks.priority < %(priority_2)s",
     {"priority_1": 0, "priority_2": 3}),
    ("priority", "lte", 2, "tasks.priority > %(priority_1)s AND tasks.priority <= %(priority_2)s",
     {"priority_1": 0, "priority_2": 2}),
    ("priority", "gt", 2, "tasks.priority > %(priority_1)s AND tasks.priority > %(priority_2)s",
     {"priority_1": 0, "priority_2": 2}),
    ("priority", "gte", 3, "tasks.priority > %(priority_1)s AND tasks.priority >= %(priority_2)s",
     {"priority_1": 0, "priority_2": 3}),
    ("priority", "in", [0, 1], "tasks.priority IN (__[POSTCOMPILE_priority_1])",
     {"priority_1": [0, 1]}),
    ("due_date", "eq", "2026-10-20", "tasks.due_date = %(due_date_1)s",
     {"due_date_1": date(2026, 10, 20)}),
    ("due_date", "lt", "@today", "tasks.due_date < %(due_date_1)s", {"due_date_1": TODAY}),
    ("due_date", "lte", "@today+7d", "tasks.due_date <= %(due_date_1)s",
     {"due_date_1": date(2026, 10, 15)}),
    ("due_date", "gt", "@today-3d", "tasks.due_date > %(due_date_1)s",
     {"due_date_1": date(2026, 10, 5)}),
    ("due_date", "gte", "@start_of_week", "tasks.due_date >= %(due_date_1)s",
     {"due_date_1": date(2026, 10, 5)}),
    ("due_date", "is_null", None, "tasks.due_date IS NULL", {}),
    ("due_date", "not_null", None, "tasks.due_date IS NOT NULL", {}),
    ("title", "contains", "логин", "tasks.title ILIKE %(title_1)s ESCAPE '\\\\'",
     {"title_1": "%логин%"}),
    ("has_parent", "eq", True, "tasks.parent_id IS NOT NULL", {}),
    ("has_parent", "eq", False, "tasks.parent_id IS NULL", {}),
    ("is_blocked", "eq", True,
     "EXISTS (SELECT * FROM task_relations, tasks AS tasks_1"
     " WHERE task_relations.target_task_id = tasks.id AND task_relations.type = %(type_1)s"
     " AND tasks_1.id = task_relations.source_task_id AND tasks_1.deleted_at IS NULL"
     " AND (tasks_1.state_id NOT IN (SELECT workflow_states.id FROM workflow_states"
     " WHERE workflow_states.type IN (__[POSTCOMPILE_type_2]))))",
     {"type_1": "blocks", "type_2": [StateType.COMPLETED, StateType.CANCELED]}),
]  # fmt: skip


def _timestamp_cases(field: str) -> list[tuple[str, str, Any, str, dict[str, Any]]]:
    """Метка времени против дня по UTC: границы — полночи соседних дней."""
    one, two = f"{field}_1", f"{field}_2"
    column = f"tasks.{field}"
    return [
        (field, "eq", "2026-10-01", f"{column} >= %({one})s AND {column} < %({two})s",
         {one: midnight(1), two: midnight(2)}),
        (field, "lt", "@today", f"{column} < %({one})s", {one: midnight(8)}),
        (field, "lte", "@today", f"{column} < %({one})s", {one: midnight(9)}),
        (field, "gt", "@today", f"{column} >= %({one})s", {one: midnight(9)}),
        (field, "gte", "@today", f"{column} >= %({one})s", {one: midnight(8)}),
        (field, "is_null", None, f"{column} IS NULL", {}),
        (field, "not_null", None, f"{column} IS NOT NULL", {}),
    ]  # fmt: skip


CASES += [case for field in ("created_at", "updated_at", "completed_at")
          for case in _timestamp_cases(field)]  # fmt: skip


@pytest.mark.parametrize(("field", "op", "value", "sql", "params"), CASES, ids=lambda x: str(x))
def test_field_and_operator_translate(
    field: str, op: str, value: Any, sql: str, params: dict[str, Any]
) -> None:
    spec = {"op": op} if value is None else {"op": op, "value": value}

    where, bound = compiled({field: spec})

    assert where == sql
    assert {key: (sorted(v) if key == "type_2" else v) for key, v in bound.items()} == {
        key: (sorted(v) if key == "type_2" else v) for key, v in params.items()
    }


def test_every_field_and_operator_is_covered() -> None:
    from app.modules.views.filters import ALLOWED_OPS

    covered = {(field, op) for field, op, *_ in CASES}
    allowed = {(str(field), str(op)) for field, ops in ALLOWED_OPS.items() for op in ops}
    assert allowed == covered


def test_conditions_are_joined_with_and() -> None:
    where, _ = compiled(
        {"priority": {"op": "eq", "value": 1}, "has_parent": {"op": "eq", "value": False}}
    )
    assert where == "tasks.priority = %(priority_1)s AND tasks.parent_id IS NULL"


def test_title_wildcards_are_escaped() -> None:
    _, params = compiled({"title": {"op": "contains", "value": "50%_off\\"}})
    assert params == {"title_1": "%50\\%\\_off\\\\%"}


@pytest.mark.parametrize(
    ("filters", "field"),
    [
        ([], "filters"),
        ({"asignee_id": {"op": "in", "value": [ID]}}, "asignee_id"),
        ({"team_id": {"op": "eq", "value": ID}}, "team_id"),
        ({"team_id": {"op": "in", "value": []}}, "team_id"),
        ({"team_id": {"op": "in", "value": ["not-a-uuid"]}}, "team_id"),
        ({"team_id": {"op": "in", "value": ["@me"]}}, "team_id"),
        ({"team_id": {"op": "in", "value": [ID] * 101}}, "team_id"),
        ({"team_id": {"value": [ID]}}, "team_id"),
        ({"team_id": {"op": "in", "value": [ID], "extra": 1}}, "team_id"),
        ({"state_type": {"op": "in", "value": ["done"]}}, "state_type"),
        ({"priority": {"op": "eq", "value": 5}}, "priority"),
        ({"priority": {"op": "eq", "value": True}}, "priority"),
        ({"priority": {"op": "eq", "value": "1"}}, "priority"),
        ({"due_date": {"op": "lt", "value": "tomorrow"}}, "due_date"),
        ({"due_date": {"op": "lt", "value": "@today+7"}}, "due_date"),
        ({"due_date": {"op": "is_null", "value": "2026-10-01"}}, "due_date"),
        ({"title": {"op": "contains", "value": "  "}}, "title"),
        ({"title": {"op": "eq", "value": "x"}}, "title"),
        ({"is_blocked": {"op": "eq", "value": "yes"}}, "is_blocked"),
    ],
)
def test_grammar_violations(filters: Any, field: str) -> None:
    with pytest.raises(FilterError) as error:
        parse_filters(filters)
    assert error.value.field == field


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("@today", date(2026, 10, 8)),
        ("@today+7d", date(2026, 10, 15)),
        ("@today-10d", date(2026, 9, 28)),
        ("@start_of_week", date(2026, 10, 5)),
        ("2026-01-31", date(2026, 1, 31)),
    ],
)
def test_dynamic_dates(value: str, expected: date) -> None:
    assert resolve_date(value, TODAY) == expected


def test_dynamic_values_resolve_at_execution() -> None:
    """Сохранённый `@today` — это «сегодня» в день выполнения, а не в день сохранения."""
    conditions = parse_filters({"due_date": {"op": "eq", "value": "@today"}})
    later = FilterContext(user_id=ME_ID, today=date(2026, 12, 31))

    (expression,) = translate(conditions, later)

    assert expression.compile(dialect=DIALECT).params == {
        "due_date_1": date(2026, 12, 31)
    }


class TestInjection:
    PAYLOAD = "'; DROP TABLE tasks; --"

    def test_value_never_reaches_sql_text(self) -> None:
        where, params = compiled({"title": {"op": "contains", "value": self.PAYLOAD}})
        assert "DROP" not in where
        assert params == {"title_1": f"%{self.PAYLOAD}%"}

    @pytest.mark.parametrize(
        "filters",
        [
            {"title; DROP TABLE tasks": {"op": "contains", "value": "x"}},
            {"title": {"op": "contains); DROP TABLE tasks; --", "value": "x"}},
            {"team_id": {"op": "in", "value": [PAYLOAD]}},
            {"priority": {"op": "eq", "value": PAYLOAD}},
            {"due_date": {"op": "eq", "value": PAYLOAD}},
        ],
    )
    def test_names_and_typed_values_are_whitelisted(self, filters: dict[str, Any]) -> None:
        with pytest.raises(FilterError):
            parse_filters(filters)
