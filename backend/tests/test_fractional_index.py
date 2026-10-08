"""Ключи ручной сортировки: порядок строк должен совпадать с задуманным порядком."""

import random

import pytest

from app.core.fractional_index import DIGITS, key_between, keys_between


def test_digits_are_in_byte_order() -> None:
    """Алфавит обязан идти по возрастанию байтов — база сравнивает с COLLATE "C"."""
    assert list(DIGITS) == sorted(DIGITS)
    assert len(DIGITS) == 62


def test_first_key() -> None:
    assert key_between(None, None) == "a0"


def test_after_and_before_first_key() -> None:
    assert key_between("a0", None) == "a1"
    assert key_between(None, "a0") == "Zz"


def test_between_neighbours_gets_longer() -> None:
    middle = key_between("a0", "a1")
    assert "a0" < middle < "a1"
    assert middle.startswith("a0")


def test_integer_part_rolls_over() -> None:
    assert key_between("az", None) == "b00"
    assert key_between(None, "Z0") == "Yzz"


@pytest.mark.parametrize(("a", "b"), [("a1", "a1"), ("a2", "a1")])
def test_rejects_unordered_bounds(a: str, b: str) -> None:
    with pytest.raises(ValueError):
        key_between(a, b)


@pytest.mark.parametrize("key", ["", "a", "a00", "!0", "a0 "])
def test_rejects_malformed_keys(key: str) -> None:
    with pytest.raises(ValueError):
        key_between(key, None)


def test_random_insertions_keep_order() -> None:
    """Тысяча вставок в случайные места: список ключей всегда отсортирован."""
    rng = random.Random(142)
    keys = [key_between(None, None)]
    for _ in range(1000):
        index = rng.randint(0, len(keys))
        before = keys[index - 1] if index > 0 else None
        after = keys[index] if index < len(keys) else None
        keys.insert(index, key_between(before, after))
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)


def test_repeated_insertion_at_one_spot_grows_slowly() -> None:
    """Худший случай — вставка всё время в одно место: порядок держится, а длина
    переходит порог перегенерации (32) лишь после полутора сотен вставок подряд."""
    low, high = "a0", "a1"
    lengths = []
    for _ in range(200):
        middle = key_between(low, high)
        assert low < middle < high
        high = middle
        lengths.append(len(high))
    assert lengths[149] <= 32 < lengths[-1]


@pytest.mark.parametrize(
    ("a", "b", "n"),
    [
        (None, None, 0),
        (None, None, 1),
        (None, None, 100),
        ("a0", None, 5),
        (None, "a0", 5),
        ("a0", "a1", 7),
    ],
)
def test_keys_between_are_ordered_and_inside_bounds(a: str | None, b: str | None, n: int) -> None:
    keys = keys_between(a, b, n)
    assert len(keys) == n
    assert keys == sorted(keys)
    assert len(set(keys)) == n
    if keys and a is not None:
        assert a < keys[0]
    if keys and b is not None:
        assert keys[-1] < b


def test_keys_between_stays_short_for_rebalance() -> None:
    """Перегенерация команды из тысячи задач даёт короткие ключи."""
    assert max(len(key) for key in keys_between(None, None, 1000)) <= 4
