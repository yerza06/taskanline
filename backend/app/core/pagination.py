"""Курсорная пагинация.

Offset на списке, куда постоянно вставляются задачи, даёт пропуски и дубли между
страницами. Курсор — base64 от ключа той же составной сортировки, что и в запросе
(например, `(sort_order, id)`): следующая страница начинается строго после него.
"""

import base64
import binascii
import json
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel

from app.core.errors import ApiError

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None
    has_more: bool


def encode_cursor(*values: Any) -> str:
    raw = json.dumps([str(value) for value in values], ensure_ascii=False)
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _invalid() -> ApiError:
    return ApiError(400, "invalid_cursor", "Курсор повреждён или устарел")


def decode_cursor(cursor: str, arity: int) -> list[str]:
    """Разбор курсора; всё, что не похоже на выданный сервером, — `400 invalid_cursor`."""
    try:
        values = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise _invalid() from error
    if (
        not isinstance(values, list)
        or len(values) != arity
        or not all(isinstance(value, str) for value in values)
    ):
        raise _invalid()
    return values


def paginate[R](
    rows: Sequence[R], limit: int, key: Callable[[R], tuple[Any, ...]]
) -> tuple[list[R], str | None, bool]:
    """Строки выбраны с `limit + 1`: лишняя строка — признак следующей страницы."""
    has_more = len(rows) > limit
    items = list(rows[:limit])
    next_cursor = encode_cursor(*key(items[-1])) if has_more and items else None
    return items, next_cursor, has_more
