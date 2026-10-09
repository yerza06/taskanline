"""Группы команд `tkl` — по одной на домен (CLI-спека §5)."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from taskanline_cli.errors import usage

Workspace = Annotated[str | None, typer.Option("--workspace", "-w", help="Slug или id workspace")]
Team = Annotated[str | None, typer.Option("--team", help="Ключ команды, например ENG")]


def text_source(value: str) -> str:
    """Текст как есть, `@путь` — из файла, `-` — из stdin."""
    if value == "-":
        return sys.stdin.read()
    if value.startswith("@"):
        path = Path(value[1:])
        try:
            return path.read_text(encoding="utf-8")
        except OSError as error:
            raise usage("file_unreadable", f"Не читается файл {path}: {error.strerror}") from error
    return value


def is_empty(value: str) -> bool:
    """`none` и `null` в опции — «очистить поле»."""
    return value.lower() in ("none", "null")


SORTS = ("manual", "priority", "due_date", "created_at", "updated_at", "title")


def parse_sort(raw: str) -> tuple[str, str]:
    """`priority`, `priority:desc` или `-priority`."""
    direction = "asc"
    if raw.startswith("-"):
        raw, direction = raw[1:], "desc"
    if ":" in raw:
        raw, direction = raw.split(":", 1)
    aliases = {"due": "due_date", "created": "created_at", "updated": "updated_at"}
    field = aliases.get(raw, raw)
    if field not in SORTS or direction not in ("asc", "desc"):
        raise usage(
            "invalid_sort", f"Неизвестная сортировка «{raw}»", f"Поля: {', '.join(SORTS)}; :desc"
        )
    return field, direction
