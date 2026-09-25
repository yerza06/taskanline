"""`console`-почта в проде: предупреждение в лог, а не тихая утечка токенов.

Бэкенд `console` пишет письмо целиком (со ссылкой из приглашения) в лог процесса.
На проде это означает, что сырой токен приглашения оседает в системе сбора логов —
`create_app()` должен предупредить об этом при старте, но не отказаться запускаться.

Предупреждение ловится подменой самого логгера, а не `structlog.testing.capture_logs`:
`structlog.configure()` — глобальное состояние процесса, и `capture_logs` конфликтует с
любым другим тестом, который успел настоящим образом сконфигурировать structlog и
воспользоваться тем же именованным логгером раньше в этом же прогоне (see AGENTS.md —
это не задокументированная особенность самого structlog, а наблюдение из отладки).
"""

from collections.abc import Iterator
from typing import Any

import pytest

import app.main as app_main
from app.core.config import get_settings


class _FakeLogger:
    """Подмена `app.main.logger`: просто копит вызовы `.warning(...)`."""

    def __init__(self) -> None:
        self.warnings: list[tuple[str, dict[str, Any]]] = []

    def warning(self, event: str, **kwargs: Any) -> None:
        self.warnings.append((event, kwargs))


@pytest.fixture(autouse=True)
def _restore_settings_cache() -> Iterator[None]:
    """`get_settings()` кэширован через `lru_cache` — тест не должен пережить себя."""
    yield
    get_settings.cache_clear()


def _create_app_with_fake_logger(monkeypatch: pytest.MonkeyPatch) -> _FakeLogger:
    fake = _FakeLogger()
    monkeypatch.setattr(app_main, "logger", fake)
    app_main.create_app()
    return fake


def test_console_mailer_in_production_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP__ENVIRONMENT", "production")
    monkeypatch.setenv("MAILER__BACKEND", "console")
    get_settings.cache_clear()

    fake = _create_app_with_fake_logger(monkeypatch)

    assert any(event == "mail.console_in_production" for event, _ in fake.warnings)


def test_smtp_mailer_in_production_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP__ENVIRONMENT", "production")
    monkeypatch.setenv("MAILER__BACKEND", "smtp")
    get_settings.cache_clear()

    fake = _create_app_with_fake_logger(monkeypatch)

    assert not any(event == "mail.console_in_production" for event, _ in fake.warnings)


def test_console_mailer_outside_production_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP__ENVIRONMENT", "ci")
    monkeypatch.setenv("MAILER__BACKEND", "console")
    get_settings.cache_clear()

    fake = _create_app_with_fake_logger(monkeypatch)

    assert not any(event == "mail.console_in_production" for event, _ in fake.warnings)
