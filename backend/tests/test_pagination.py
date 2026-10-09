"""Курсор — непрозрачная строка поверх ключа сортировки и id."""

from uuid import UUID

import pytest

from app.core.errors import ApiError
from app.core.pagination import decode_cursor, encode_cursor, paginate

ID = UUID("019a5c1e-0000-7000-8000-000000000001")


def test_cursor_round_trip() -> None:
    cursor = encode_cursor("a0V", ID)
    assert decode_cursor(cursor, 2) == ["a0V", str(ID)]


def test_cursor_is_url_safe() -> None:
    cursor = encode_cursor("ÿÿÿ" * 10, ID)
    assert set(cursor) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=")


@pytest.mark.parametrize("garbage", ["", "!!!", "bm90IGpzb24", encode_cursor("a0"), "W10="])
def test_garbage_cursor_is_client_error(garbage: str) -> None:
    with pytest.raises(ApiError) as caught:
        decode_cursor(garbage, 2)
    assert caught.value.status_code == 400
    assert caught.value.code == "invalid_cursor"


def test_paginate_cuts_extra_row_and_points_to_last_item() -> None:
    rows = ["a", "b", "c"]
    items, next_cursor, has_more = paginate(rows, 2, lambda row: (row, ID))
    assert items == ["a", "b"]
    assert has_more is True
    assert next_cursor is not None
    assert decode_cursor(next_cursor, 2) == ["b", str(ID)]


def test_paginate_last_page_has_no_cursor() -> None:
    items, next_cursor, has_more = paginate(["a"], 2, lambda row: (row, ID))
    assert items == ["a"]
    assert (next_cursor, has_more) == (None, False)
