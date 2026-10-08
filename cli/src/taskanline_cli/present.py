"""Как объекты API выглядят в выводе CLI.

Задача в списке — компактная (CLI-спека §7): ключ, заголовок, статус, исполнитель,
приоритет, срок, метки, проект и `url`. Поле, которого нет, присутствует со значением
`null`, а не исчезает: структура вывода одна при любых данных.
"""

from typing import Any

from pydantic import BaseModel

from taskanline_cli.output import Column, Item, Listing, col
from taskanline_sdk.models import Task

PRIORITY_NAMES = {0: "none", 1: "urgent", 2: "high", 3: "medium", 4: "low"}
# Поля задачи, которые нужно развернуть, чтобы показать её компактно.
TASK_EXPAND = ("state", "assignee", "labels", "project")
DETAIL_EXPAND = (*TASK_EXPAND, "creator", "parent", "relations")


def dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def compact_task(task: Task, web_url: str) -> dict[str, Any]:
    return {
        "key": task.key,
        "title": task.title,
        "state": {"name": task.state.name, "type": task.state.type} if task.state else None,
        "assignee": (
            {"email": task.assignee.email, "name": task.assignee.full_name}
            if task.assignee
            else None
        ),
        "priority": PRIORITY_NAMES.get(task.priority, str(task.priority)),
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "labels": [label.name for label in task.labels or []],
        "project": task.project.name if task.project else None,
        "url": f"{web_url}/{task.key}",
    }


def full_task(task: Task, web_url: str) -> dict[str, Any]:
    return {
        **compact_task(task, web_url),
        "id": str(task.id),
        "description": task.description,
        "creator": (
            {"email": task.creator.email, "name": task.creator.full_name} if task.creator else None
        ),
        "parent": task.parent.key if task.parent else None,
        "relations": [
            {"type": relation.type, "task": relation.task.key, "id": str(relation.id)}
            for relation in task.relations or []
        ],
        "started_at": _iso(task.started_at),
        "completed_at": _iso(task.completed_at),
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
        "deleted_at": _iso(task.deleted_at),
    }


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _priority_style(value: Any) -> str:
    return {"urgent": "bold red", "high": "yellow"}.get(str(value), "")


def _state_style(value: Any) -> str:
    kind = value.get("type") if isinstance(value, dict) else None
    return {"started": "cyan", "completed": "green", "canceled": "dim"}.get(str(kind), "")


TASK_COLUMNS = [
    col("KEY", "key"),
    col("STATE", "state", _state_style),
    col("PRIORITY", "priority", _priority_style),
    col("TITLE", "title"),
    Column("ASSIGNEE", lambda row: (row.get("assignee") or {}).get("email")),
]


def task_listing(
    tasks: list[Task],
    web_url: str,
    *,
    next_cursor: str | None = None,
    has_more: bool = False,
    total_hint: int | None = None,
) -> Listing:
    return Listing(
        [compact_task(task, web_url) for task in tasks],
        TASK_COLUMNS,
        ident="key",
        next_cursor=next_cursor,
        has_more=has_more,
        total_hint=total_hint,
    )


def task_item(task: Task, web_url: str, **extra: Any) -> Item:
    return Item({**full_task(task, web_url), **extra}, ident="key")


def listing(
    models: list[Any], columns: list[Column], *, ident: str = "id", **extra: Any
) -> Listing:
    return Listing([dump(model) for model in models], columns, ident=ident, extra=extra)
