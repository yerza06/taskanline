"""Дробный индекс для ручной сортировки (`tasks.sort_order`).

Ключ — строка в base62, лексикографический порядок которой и есть порядок задач.
Вставка между соседями — новый ключ между их ключами, без перенумерации остальных.

Порт алгоритма rocicorp/fractional-indexing (CC0). Ключ состоит из целой части
переменной длины (первый символ задаёт её длину: `a` — два символа, `b` — три,
`Z` — два символа «отрицательной» части, `Y` — три) и дробной части без хвостовых
нулей. Целая часть растёт при добавлении в конец, дробная — при вставке между.

Алфавит упорядочен по байтам, поэтому колонка в базе обязана сравниваться
побайтово (`COLLATE "C"`): лингвистическая коллация ставит `a` перед `B`.
"""

DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_ZERO = DIGITS[0]
_LAST = DIGITS[-1]
# Наименьшая целая часть: ниже неё ключей не бывает.
_SMALLEST_INTEGER = "A" + _ZERO * 26


def _midpoint(a: str, b: str | None) -> str:
    """Дробная часть строго между `a` и `b` (`b=None` — без верхней границы)."""
    if b is not None and a >= b:
        raise ValueError(f"{a!r} >= {b!r}")
    if a.endswith(_ZERO) or (b is not None and b.endswith(_ZERO)):
        raise ValueError("дробная часть с хвостовым нулём")
    if b is not None:
        # Общий префикс переносится как есть, середина ищется после него.
        n = 0
        while (a[n] if n < len(a) else _ZERO) == b[n]:
            n += 1
        if n > 0:
            return b[:n] + _midpoint(a[n:], b[n:])

    digit_a = DIGITS.index(a[0]) if a else 0
    digit_b = DIGITS.index(b[0]) if b is not None else len(DIGITS)
    if digit_b - digit_a > 1:
        # Округление половины вверх — как Math.round в исходном алгоритме.
        return DIGITS[(digit_a + digit_b + 1) // 2]
    if b is not None and len(b) > 1:
        return b[:1]
    return DIGITS[digit_a] + _midpoint(a[1:], None)


def _integer_length(head: str) -> int:
    if "a" <= head <= "z":
        return ord(head) - ord("a") + 2
    if "A" <= head <= "Z":
        return ord("Z") - ord(head) + 2
    raise ValueError(f"недопустимый первый символ ключа: {head!r}")


def _integer_part(key: str) -> str:
    length = _integer_length(key[0])
    if length > len(key):
        raise ValueError(f"ключ короче своей целой части: {key!r}")
    return key[:length]


def _validate(key: str) -> None:
    if not key:
        raise ValueError("пустой ключ")
    if key == _SMALLEST_INTEGER:
        raise ValueError("ключ вне допустимого диапазона")
    if any(char not in DIGITS for char in key):
        raise ValueError(f"недопустимый символ в ключе: {key!r}")
    integer = _integer_part(key)
    if key[len(integer) :].endswith(_ZERO):
        raise ValueError(f"дробная часть с хвостовым нулём: {key!r}")


def _increment(integer: str) -> str | None:
    head, digits = integer[0], list(integer[1:])
    for i in range(len(digits) - 1, -1, -1):
        d = DIGITS.index(digits[i]) + 1
        if d < len(DIGITS):
            digits[i] = DIGITS[d]
            return head + "".join(digits)
        digits[i] = _ZERO
    # Перенос из старшего разряда: целая часть удлиняется (или меняет знак).
    if head == "Z":
        return "a" + _ZERO
    if head == "z":
        return None
    new_head = chr(ord(head) + 1)
    if new_head > "a":
        digits.append(_ZERO)
    else:
        digits.pop()
    return new_head + "".join(digits)


def _decrement(integer: str) -> str | None:
    head, digits = integer[0], list(integer[1:])
    for i in range(len(digits) - 1, -1, -1):
        d = DIGITS.index(digits[i]) - 1
        if d >= 0:
            digits[i] = DIGITS[d]
            return head + "".join(digits)
        digits[i] = _LAST
    if head == "a":
        return "Z" + _LAST
    if head == "A":
        return None
    new_head = chr(ord(head) - 1)
    if new_head < "Z":
        digits.append(_LAST)
    else:
        digits.pop()
    return new_head + "".join(digits)


def key_between(a: str | None, b: str | None) -> str:
    """Ключ строго между `a` и `b`; `None` — граница открыта с этой стороны."""
    if a is not None:
        _validate(a)
    if b is not None:
        _validate(b)
    if a is not None and b is not None and a >= b:
        raise ValueError(f"{a!r} >= {b!r}")

    if a is None:
        if b is None:
            return "a" + _ZERO
        int_b = _integer_part(b)
        frac_b = b[len(int_b) :]
        if int_b == _SMALLEST_INTEGER:
            return int_b + _midpoint("", frac_b)
        if int_b < b:
            return int_b
        decremented = _decrement(int_b)
        if decremented is None:
            raise ValueError("ключей меньше этого нет")
        return decremented

    int_a = _integer_part(a)
    frac_a = a[len(int_a) :]
    if b is None:
        incremented = _increment(int_a)
        return int_a + _midpoint(frac_a, None) if incremented is None else incremented

    int_b = _integer_part(b)
    frac_b = b[len(int_b) :]
    if int_a == int_b:
        return int_a + _midpoint(frac_a, frac_b)
    incremented = _increment(int_a)
    if incremented is None:
        raise ValueError("ключей больше этого нет")
    if incremented < b:
        return incremented
    return int_a + _midpoint(frac_a, None)


def keys_between(a: str | None, b: str | None, n: int) -> list[str]:
    """`n` возрастающих ключей между `a` и `b` — для перегенерации целой команды."""
    if n <= 0:
        return []
    if n == 1:
        return [key_between(a, b)]
    if b is None:
        keys = [key_between(a, None)]
        for _ in range(n - 1):
            keys.append(key_between(keys[-1], None))
        return keys
    if a is None:
        keys = [key_between(None, b)]
        for _ in range(n - 1):
            keys.append(key_between(None, keys[-1]))
        return list(reversed(keys))
    middle_index = n // 2
    middle = key_between(a, b)
    return [
        *keys_between(a, middle, middle_index),
        middle,
        *keys_between(middle, b, n - middle_index - 1),
    ]
