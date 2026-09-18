"""Скользящее окно в памяти процесса. Время подменяется, ничего не ждём."""

from app.core.rate_limit import InMemoryRateLimiter


class Clock:
    """Управляемое время: тест двигает его сам, а не спит."""

    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class TestInMemoryRateLimiter:
    def test_allows_up_to_limit(self) -> None:
        limiter = InMemoryRateLimiter(clock=Clock())

        results = [limiter.hit("ip", limit=3, window_seconds=60) for _ in range(3)]

        assert all(result.allowed for result in results)
        assert all(result.retry_after == 0 for result in results)

    def test_blocks_over_limit_and_reports_retry_after(self) -> None:
        limiter = InMemoryRateLimiter(clock=Clock())
        for _ in range(3):
            limiter.hit("ip", limit=3, window_seconds=60)

        result = limiter.hit("ip", limit=3, window_seconds=60)

        assert result.allowed is False
        assert result.retry_after == 60

    def test_retry_after_shrinks_as_window_moves(self) -> None:
        clock = Clock()
        limiter = InMemoryRateLimiter(clock=clock)
        for _ in range(3):
            limiter.hit("ip", limit=3, window_seconds=60)

        clock.value = 30.0
        result = limiter.hit("ip", limit=3, window_seconds=60)

        assert result.allowed is False
        assert result.retry_after == 30

    def test_window_slides(self) -> None:
        clock = Clock()
        limiter = InMemoryRateLimiter(clock=clock)
        for _ in range(3):
            limiter.hit("ip", limit=3, window_seconds=60)

        clock.value = 61.0

        assert limiter.hit("ip", limit=3, window_seconds=60).allowed is True

    def test_blocked_attempt_does_not_extend_the_ban(self) -> None:
        """Отклонённая попытка не должна попадать в окно: иначе бан самоподдерживается."""
        clock = Clock()
        limiter = InMemoryRateLimiter(clock=clock)
        for _ in range(3):
            limiter.hit("ip", limit=3, window_seconds=60)

        clock.value = 59.0
        limiter.hit("ip", limit=3, window_seconds=60)
        clock.value = 61.0

        assert limiter.hit("ip", limit=3, window_seconds=60).allowed is True

    def test_keys_are_independent(self) -> None:
        limiter = InMemoryRateLimiter(clock=Clock())
        for _ in range(3):
            limiter.hit("a", limit=3, window_seconds=60)

        assert limiter.hit("b", limit=3, window_seconds=60).allowed is True

    def test_expired_keys_do_not_accumulate(self) -> None:
        """Окно, из которого всё вышло, не должно оставлять запись навсегда."""
        clock = Clock()
        limiter = InMemoryRateLimiter(clock=clock)
        limiter.hit("a", limit=3, window_seconds=60)

        clock.value = 1000.0
        limiter.hit("b", limit=3, window_seconds=60)

        assert limiter.tracked_keys() == ["b"]

    def test_reset_clears_everything(self) -> None:
        limiter = InMemoryRateLimiter(clock=Clock())
        for _ in range(3):
            limiter.hit("ip", limit=3, window_seconds=60)

        limiter.reset()

        assert limiter.hit("ip", limit=3, window_seconds=60).allowed is True
