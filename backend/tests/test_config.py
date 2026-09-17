"""Настройки разбираются группами, а не одной плоской кучей."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

DB_ENV = {
    "DB__USER": "taskanline",
    "DB__PASSWORD": "secret",
    "DB__HOST": "db.example",
    "DB__PORT": "6432",
    "DB__NAME": "taskanline",
}
VALID_SECRET = "a" * 32
GROUP_PREFIXES = ("DB__", "SECURITY__", "APP__", "LOG__", "CORS__", "SERVER__")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Окружение разработчика не должно просачиваться в тесты настроек."""
    for key in list(os.environ):
        if key.startswith(GROUP_PREFIXES):
            monkeypatch.delenv(key, raising=False)


def build(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    """Собирает Settings из чистого окружения, игнорируя .env разработчика."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def build_valid(monkeypatch: pytest.MonkeyPatch, **extra: str) -> Settings:
    """Валидный минимум, поверх которого тест меняет одно-два значения."""
    return build(monkeypatch, **{**DB_ENV, "SECURITY__SECRET_KEY": VALID_SECRET, **extra})


class TestDatabase:
    def test_url_is_composed_from_parts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = build_valid(monkeypatch)

        assert (
            settings.db.url == "postgresql+asyncpg://taskanline:secret@db.example:6432/taskanline"
        )

    def test_driver_defaults_to_asyncpg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = build_valid(monkeypatch)

        assert settings.db.driver == "postgresql+asyncpg"

    def test_special_characters_in_password_are_escaped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings = build_valid(monkeypatch, DB__PASSWORD="p@ss:w/ord")

        assert "p%40ss%3Aw%2Ford" in settings.db.url
        assert settings.db.url.endswith("@db.example:6432/taskanline")

    def test_sync_driver_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with pytest.raises(ValidationError, match="async"):
            build_valid(monkeypatch, DB__DRIVER="postgresql+psycopg2")

    def test_port_must_be_a_number(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with pytest.raises(ValidationError):
            build_valid(monkeypatch, DB__PORT="не число")

    def test_missing_required_fields_fail_at_startup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with pytest.raises(ValidationError) as error:
            build(monkeypatch, SECURITY__SECRET_KEY=VALID_SECRET)

        assert any(item["loc"][0] == "db" for item in error.value.errors())

    def test_password_is_hidden_in_repr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Настройки попадают и в логи, и в трейсбеки — пароль там не нужен."""
        settings = build_valid(monkeypatch)

        assert "secret" not in repr(settings.db)


class TestCors:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = build_valid(monkeypatch)

        assert settings.cors.origins == ["http://localhost:5173"]
        assert settings.cors.allow_credentials is True
        assert settings.cors.allow_methods == ["*"]
        assert settings.cors.allow_headers == ["*"]

    def test_lists_accept_comma_separated_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = build_valid(
            monkeypatch,
            CORS__ORIGINS="http://a.example, http://b.example",
            CORS__ALLOW_METHODS="GET, POST",
        )

        assert settings.cors.origins == ["http://a.example", "http://b.example"]
        assert settings.cors.allow_methods == ["GET", "POST"]

    def test_lists_accept_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = build_valid(monkeypatch, CORS__ORIGINS='["http://a.example"]')

        assert settings.cors.origins == ["http://a.example"]

    def test_flag_is_parsed_as_boolean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = build_valid(monkeypatch, CORS__ALLOW_CREDENTIALS="false")

        assert settings.cors.allow_credentials is False


class TestEnvExample:
    """Пример конфигурации обязан оставаться рабочим, а не историческим."""

    @staticmethod
    def _example() -> dict[str, str]:
        from dotenv import dotenv_values

        path = Path(__file__).resolve().parents[2] / ".env.example"
        return {key: value for key, value in dotenv_values(path).items() if value is not None}

    def test_settings_build_from_example_as_is(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = build(monkeypatch, **self._example())

        assert settings.db.url.startswith("postgresql+asyncpg://taskanline:")
        assert settings.server.port == 8000

    def test_example_covers_every_group(self) -> None:
        keys = self._example()

        for prefix in GROUP_PREFIXES:
            assert any(key.startswith(prefix) for key in keys), f"в примере нет ни одной {prefix}*"

    def test_example_covers_every_field(self) -> None:
        """Поле, добавленное в настройки и забытое в примере, — ловушка при разворачивании."""
        keys = set(self._example())

        missing = {
            f"{group.upper()}__{field.upper()}"
            for group, model in Settings.model_fields.items()
            for field in model.annotation.model_fields  # type: ignore[union-attr]
        } - keys

        assert not missing, f"в .env.example не хватает: {sorted(missing)}"


class TestOtherGroups:
    def test_groups_with_defaults_need_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = build_valid(monkeypatch)

        assert settings.app.environment == "local"
        assert settings.log.level == "INFO"
        assert settings.server.host == "0.0.0.0"
        assert settings.server.port == 8000
        assert settings.server.reload is False

    def test_values_come_from_nested_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = build_valid(
            monkeypatch,
            APP__ENVIRONMENT="production",
            LOG__LEVEL="DEBUG",
            SERVER__PORT="9000",
            SERVER__RELOAD="true",
        )

        assert settings.app.environment == "production"
        assert settings.log.level == "DEBUG"
        assert settings.server.port == 9000
        assert settings.server.reload is True

    def test_short_secret_key_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with pytest.raises(ValidationError):
            build_valid(monkeypatch, SECURITY__SECRET_KEY="короткий")
