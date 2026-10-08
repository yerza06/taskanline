"""Форматы вывода: json | table | plain | quiet (CLI-спека §7).

Формат выбирается сам: stdout — терминал → `table`, иначе → `json`. `TKL_OUTPUT` и
явные опции перекрывают выбор. В stdout идут только данные — всё остальное в stderr,
поэтому `tkl task list > out.json` даёт валидный JSON всегда.
"""

import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from rich.console import Console
from rich.table import Table


class Format(StrEnum):
    JSON = "json"
    TABLE = "table"
    PLAIN = "plain"
    QUIET = "quiet"


def choose_format(*, explicit: str | None, json_flag: bool, quiet: bool) -> Format:
    if quiet:
        return Format.QUIET
    if explicit:
        return Format(explicit)
    if json_flag:
        return Format.JSON
    env = os.environ.get("TKL_OUTPUT")
    if env in {item.value for item in Format}:
        return Format(env)
    return Format.TABLE if sys.stdout.isatty() else Format.JSON


@dataclass(frozen=True)
class Column:
    header: str
    get: Callable[[dict[str, Any]], Any]
    style: Callable[[Any], str] | None = None


def col(header: str, key: str, style: Callable[[Any], str] | None = None) -> Column:
    return Column(header, lambda row: row.get(key), style)


@dataclass
class Item:
    """Одиночный объект — выводится без обёртки."""

    data: dict[str, Any]
    ident: str = "id"


@dataclass
class Listing:
    """Список — всегда в обёртке с метаданными пагинации."""

    items: list[dict[str, Any]]
    columns: list[Column]
    ident: str = "id"
    next_cursor: str | None = None
    has_more: bool = False
    total_hint: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


Result = Item | Listing


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("name") or value.get("email") or value.get("key") or value)
    if isinstance(value, list):
        return ",".join(_text(item) for item in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _plain(value: Any) -> str:
    # Табуляция и перевод строки в значении сломали бы разбор awk и cut.
    return _text(value).replace("\t", " ").replace("\n", " ")


def render(result: Result, fmt: Format, *, color: bool = True) -> None:
    out = sys.stdout
    if fmt == Format.JSON:
        if isinstance(result, Listing):
            payload: Any = {
                "items": result.items,
                "next_cursor": result.next_cursor,
                "has_more": result.has_more,
                "total_hint": result.total_hint,
                **result.extra,
            }
        else:
            payload = result.data
        indent = 2 if out.isatty() else None
        out.write(json.dumps(payload, ensure_ascii=False, indent=indent, default=str) + "\n")
    elif fmt == Format.QUIET:
        rows = result.items if isinstance(result, Listing) else [result.data]
        for row in rows:
            out.write(_text(row.get(result.ident)) + "\n")
    elif fmt == Format.PLAIN:
        if isinstance(result, Listing):
            for row in result.items:
                out.write("\t".join(_plain(c.get(row)) for c in result.columns) + "\n")
        else:
            for key, value in result.data.items():
                out.write(f"{key}\t{_plain(value)}\n")
    else:
        _table(result, color=color)


def _table(result: Result, *, color: bool) -> None:
    console = Console(file=sys.stdout, no_color=not color, highlight=False, soft_wrap=False)
    if isinstance(result, Item):
        table = Table(show_header=False, box=None, pad_edge=False)
        table.add_column(style="bold")
        table.add_column(overflow="fold")
        for key, value in result.data.items():
            text = (
                json.dumps(value, ensure_ascii=False, default=str)
                if isinstance(value, list | dict) and not _flat(value)
                else _text(value)
            )
            table.add_row(key, text or "—")
        console.print(table)
        return
    table = Table(box=None, pad_edge=False, header_style="bold")
    for column in result.columns:
        table.add_column(column.header, overflow="fold")
    for row in result.items:
        cells = []
        for column in result.columns:
            value = column.get(row)
            text = _text(value) or "—"
            cells.append(
                f"[{column.style(value)}]{_escape(text)}[/]"
                if column.style and column.style(value)
                else _escape(text)
            )
        table.add_row(*cells)
    console.print(table)
    if result.has_more and result.next_cursor:
        Console(stderr=True, no_color=not color).print(
            f"Есть ещё. Следующая страница: --cursor {result.next_cursor}", highlight=False
        )


def _flat(value: Any) -> bool:
    """Список имён или объект-ссылка читаются одной строкой и без JSON."""
    if isinstance(value, dict):
        return bool(value.get("name") or value.get("email") or value.get("key"))
    return all(not isinstance(item, list | dict) or _flat(item) for item in value)


def _escape(text: str) -> str:
    return text.replace("[", "\\[")


def info(message: str) -> None:
    """Служебное сообщение человеку — в stderr, чтобы не портить данные в stdout."""
    sys.stderr.write(message + "\n")
