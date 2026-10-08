"""Как объекты выглядят для модели: минимум полей, ключи вместо UUID, жёсткие потолки.

Ответ, занимающий тысячи токенов, вытесняет из контекста саму задачу, ради которой его
запросили (MCP-спека §3). Поэтому описание в списке — до 200 символов, комментарии и
события — последние 20.
"""

from typing import Any

from taskanline_sdk.models import Task

PRIORITY_NAMES = {0: "none", 1: "urgent", 2: "high", 3: "medium", 4: "low"}
PRIORITY_VALUES = {name: value for value, name in PRIORITY_NAMES.items()}
DESCRIPTION_LIMIT = 200
TAIL_LIMIT = 20
TASK_EXPAND = ("state", "assignee", "labels", "project")
DETAIL_EXPAND = (*TASK_EXPAND, "parent", "relations")


def clip(text: str | None, limit: int = DESCRIPTION_LIMIT) -> str | None:
    if text is None or len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def task_brief(task: Task, web_url: str) -> dict[str, Any]:
    """Задача в списке."""
    return {
        "key": task.key,
        "title": task.title,
        "state": task.state.name if task.state else None,
        "state_type": task.state.type if task.state else None,
        "assignee": task.assignee.email if task.assignee else None,
        "priority": PRIORITY_NAMES.get(task.priority, str(task.priority)),
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "labels": [label.name for label in task.labels or []],
        "project": task.project.name if task.project else None,
        "description": clip(task.description),
        "url": f"{web_url}/{task.key}",
    }


def task_card(task: Task, web_url: str) -> dict[str, Any]:
    """Карточка задачи: полное описание, родитель и связи."""
    return {
        **task_brief(task, web_url),
        "description": task.description,
        "parent": task.parent.key if task.parent else None,
        "relations": [
            {"type": relation.type, "task": relation.task.key, "title": relation.task.title}
            for relation in task.relations or []
        ],
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }
