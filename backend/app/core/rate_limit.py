"""Ограничение частоты запросов — в памяти процесса и точечно.

Redis появится на этапе 9, и до тех пор общего распределённого лимита нет. Это
осознанный размен: скользящее окно в памяти защищает от перебора паролей, и
этого достаточно, пока API рассчитан на один процесс. При нескольких воркерах
лимит станет пер-воркерным — то есть менее строгим, но не сломанным.

Интерфейс синхронный: ждать в памяти нечего, а `async` здесь создавал бы
видимость, что реализацию можно подменить на Redis простой заменой класса.
Нельзя — у распределённой версии будет другая семантика, и она придёт вместе с
остальным этапом 9.
"""

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: int
    """Секунды до следующей разрешённой попытки; 0, когда попытка разрешена."""


class RateLimiter(Protocol):
    def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult: ...

    def reset(self) -> None: ...


class InMemoryRateLimiter:
    """Скользящее окно: на каждый ключ — очередь меток времени внутри окна."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        now = self._clock()
        self._drop_expired(now, window_seconds)

        hits = self._hits.setdefault(key, deque())
        if len(hits) >= limit:
            # Отклонённая попытка в окно не записывается: иначе перебор
            # продлевал бы собственный бан бесконечно.
            elapsed = now - hits[0]
            return RateLimitResult(
                allowed=False,
                retry_after=max(1, math.ceil(window_seconds - elapsed)),
            )

        hits.append(now)
        return RateLimitResult(allowed=True, retry_after=0)

    def reset(self) -> None:
        self._hits.clear()

    def tracked_keys(self) -> list[str]:
        """Ключи, за которыми лимитер сейчас следит. Нужен тестам на утечку памяти."""
        return list(self._hits)

    def _drop_expired(self, now: float, window_seconds: int) -> None:
        """Чистка на каждом обращении: иначе словарь растёт по числу увиденных адресов."""
        for key in list(self._hits):
            hits = self._hits[key]
            while hits and now - hits[0] >= window_seconds:
                hits.popleft()
            if not hits:
                del self._hits[key]
