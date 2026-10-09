"""Мини-DSL фильтров `--filter` (CLI-спека §6).

    assignee:me state-type:!completed,!canceled priority:<=2 due:<@today+7d title~логин

Условия через пробел соединяются через AND, значения через запятую — через OR. Разбор
синтаксический и до сети: ошибка сообщает позицию и подсказывает похожее поле. Имена
(ключ команды, статус, метка, email) превращаются в id позже, запросами к API, —
`compile` в `context.py`; здесь только форма.
"""

import difflib
import re
from dataclasses import dataclass
from enum import StrEnum

FIELDS = (
    "team",
    "project",
    "state",
    "state-type",
    "assignee",
    "creator",
    "label",
    "priority",
    "due",
    "created",
    "updated",
    "parent",
    "title",
)
COMPARABLE = frozenset({"priority", "due", "created", "updated"})
NULLABLE = frozenset({"project", "assignee", "due", "parent"})
SINGLE_VALUE = frozenset({"due", "created", "updated"})
STATE_TYPES = ("backlog", "unstarted", "started", "completed", "canceled")
PRIORITIES = {"none": 0, "urgent": 1, "high": 2, "medium": 3, "low": 4}
DATE_VALUE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}|@today(?:[+-]\d{1,4}d)?|@week)$")
_TOKEN = re.compile(r"""(?:"[^"]*"|'[^']*'|\S)+""")
_TERM = re.compile(r"^([a-z][a-z-]*)(~|:)(.*)$", re.DOTALL)


class Op(StrEnum):
    IN = "in"
    NIN = "nin"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    IS_NULL = "is_null"
    NOT_NULL = "not_null"
    CONTAINS = "contains"


_COMPARISONS = (("<=", Op.LTE), (">=", Op.GTE), ("<", Op.LT), (">", Op.GT))


@dataclass(frozen=True)
class Term:
    """Одно условие: поле DSL, оператор и значения как их написал пользователь."""

    field: str
    op: Op
    values: tuple[str, ...]
    position: int


class FilterSyntaxError(ValueError):
    def __init__(
        self, text: str, position: int, message: str, suggestion: str | None = None
    ) -> None:
        super().__init__(message)
        self.text = text
        self.position = position
        self.message = message
        self.suggestion = suggestion

    def render(self) -> str:
        lines = [
            f"Ошибка в фильтре на позиции {self.position}: {self.message}.",
            f"  {self.text}",
            "  " + " " * self.position + "^",
        ]
        if self.suggestion:
            lines.append(f"Возможно, вы имели в виду: {self.suggestion}")
        return "\n".join(lines)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value.replace('"', "").replace("'", "")


def _split_values(raw: str) -> list[str]:
    """`a,"b, c",d` → три значения: запятая в кавычках — часть значения."""
    parts, current, quote = [], "", ""
    for char in raw:
        if quote:
            current += char
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
            current += char
        elif char == ",":
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return [_unquote(part.strip()) for part in parts]


def parse(text: str) -> list[Term]:
    terms: list[Term] = []
    seen: set[str] = set()
    for match in _TOKEN.finditer(text):
        token, start = match.group(), match.start()
        term = _TERM.match(token)
        if term is None:
            raise FilterSyntaxError(text, start, f"ожидалось поле:значение, получено «{token}»")
        name, sign, raw = term.groups()
        value_at = start + len(name) + 1
        if name not in FIELDS:
            close = difflib.get_close_matches(name, FIELDS, n=1, cutoff=0.6)
            raise FilterSyntaxError(
                text, start, f"неизвестное поле «{name}»", close[0] if close else None
            )
        if name in seen:
            raise FilterSyntaxError(text, start, f"поле «{name}» указано дважды")
        seen.add(name)
        if not raw:
            raise FilterSyntaxError(text, value_at, f"пустое значение поля «{name}»")
        if sign == "~":
            if name != "title":
                raise FilterSyntaxError(
                    text, start + len(name), "подстрока «~» допустима только для title"
                )
            terms.append(Term(name, Op.CONTAINS, (_unquote(raw),), start))
            continue
        if name == "title":
            raise FilterSyntaxError(
                text, start + len(name), "title ищется подстрокой", f"title~{_unquote(raw)}"
            )
        terms.append(_term(text, name, raw, start, value_at))
    return terms


def _term(text: str, name: str, raw: str, start: int, value_at: int) -> Term:
    if raw in ("null", "!null"):
        if name not in NULLABLE:
            raise FilterSyntaxError(text, value_at, f"поле «{name}» не бывает пустым")
        return Term(name, Op.IS_NULL if raw == "null" else Op.NOT_NULL, (), start)

    for prefix, op in _COMPARISONS:
        if raw.startswith(prefix):
            if name not in COMPARABLE:
                raise FilterSyntaxError(text, value_at, f"сравнение недопустимо для поля «{name}»")
            value = _unquote(raw[len(prefix) :])
            _check_value(text, name, value, value_at + len(prefix))
            return Term(name, op, (value,), start)

    values = _split_values(raw)
    negated = [value.startswith("!") for value in values]
    if any(negated) and not all(negated):
        raise FilterSyntaxError(text, value_at, "отрицание — у всех значений поля или ни у одного")
    clean = tuple(value[1:] if value.startswith("!") else value for value in values)
    if any(not value for value in clean):
        raise FilterSyntaxError(text, value_at, f"пустое значение в списке поля «{name}»")
    if name in SINGLE_VALUE and (len(clean) > 1 or all(negated)):
        raise FilterSyntaxError(
            text, value_at, f"поле «{name}» сравнивается с одной датой: {name}:>@today"
        )
    for value in clean:
        _check_value(text, name, value, value_at)
    return Term(name, Op.NIN if all(negated) else Op.IN, clean, start)


def _check_value(text: str, name: str, value: str, at: int) -> None:
    if name == "state-type" and value not in STATE_TYPES:
        close = difflib.get_close_matches(value, STATE_TYPES, n=1)
        raise FilterSyntaxError(
            text, at, f"неизвестный тип статуса «{value}»", close[0] if close else None
        )
    if name == "priority" and value not in PRIORITIES and value not in {"0", "1", "2", "3", "4"}:
        raise FilterSyntaxError(
            text, at, f"приоритет — {', '.join(PRIORITIES)} или 0–4, получено «{value}»"
        )
    if name in SINGLE_VALUE and not DATE_VALUE.match(value):
        raise FilterSyntaxError(
            text, at, f"ожидалась дата YYYY-MM-DD, @today±Nd или @week, получено «{value}»"
        )


def priority_value(value: str) -> int:
    return PRIORITIES[value] if value in PRIORITIES else int(value)


def date_value(value: str) -> str:
    """`@week` в DSL — `@start_of_week` в грамматике views."""
    return "@start_of_week" if value == "@week" else value
