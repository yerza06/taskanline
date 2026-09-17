"""Настройки разбираются группами, а не одной плоской кучей."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

VALID_URL = "postgresql+asyncpg://user:pass@localhost:5432/db"
VALID_SECRET = "a" * 32


def build(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    """Собирает Settings из чистого окружения, игнорируя .env разработчика."""
    for key in list(env):
        monkeypatch.setenv(key, env[key])
    return Settings(_env_file=None)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "DB__URL",
        "SECURITY__SECRET_KEY",
        "APP__ENVIRONMENT",
        "APP__PUBLIC_URL",
        "APP__CORS_ORIGINS",
        "LOG__LEVEL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_groups_are_filled_from_nested_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = build(
        monkeypatch,
        DB__URL=VALID_URL,
        SECURITY__SECRET_KEY=VALID_SECRET,
        APP__ENVIRONMENT="production",
        LOG__LEVEL="DEBUG",
    )

    assert settings.db.url == VALID_URL
    assert settings.security.secret_key == VALID_SECRET
    assert settings.app.environment == "production"
    assert settings.log.level == "DEBUG"


def test_optional_groups_have_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = build(monkeypatch, DB__URL=VALID_URL, SECURITY__SECRET_KEY=VALID_SECRET)

    assert settings.app.environment == "local"
    assert settings.app.public_url == "http://localhost:5173"
    assert settings.log.level == "INFO"


def test_cors_origins_accept_comma_separated_string(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = build(
        monkeypatch,
        DB__URL=VALID_URL,
        SECURITY__SECRET_KEY=VALID_SECRET,
        APP__CORS_ORIGINS="http://a.example, http://b.example",
    )

    assert settings.app.cors_origins == ["http://a.example", "http://b.example"]


def test_cors_origins_accept_json_list(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = build(
        monkeypatch,
        DB__URL=VALID_URL,
        SECURITY__SECRET_KEY=VALID_SECRET,
        APP__CORS_ORIGINS='["http://a.example"]',
    )

    assert settings.app.cors_origins == ["http://a.example"]


def test_sync_database_driver_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="asyncpg"):
        build(
            monkeypatch,
            DB__URL="postgresql://user:pass@localhost:5432/db",
            SECURITY__SECRET_KEY=VALID_SECRET,
        )


def test_short_secret_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        build(monkeypatch, DB__URL=VALID_URL, SECURITY__SECRET_KEY="слишком короткий")


def test_missing_required_groups_fail_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError) as error:
        build(monkeypatch)

    reported = {tuple(item["loc"]) for item in error.value.errors()}
    assert ("db",) in reported or ("db", "url") in reported
