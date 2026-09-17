"""Настройки приложения.

Единственный источник конфигурации: всё, что приходит извне, проходит через `Settings`
и проверяется при старте, а не в момент первого обращения где-то в глубине кода.

Настройки разложены по группам — по одной `BaseModel` на область ответственности.
Плоский список из двадцати полей к этапу 6 превращается в свалку, где `secret_key`
стоит рядом с `log_level` и ничто не подсказывает, что с чем связано. Группа заодно
задаёт префикс переменной окружения: `DB__URL`, `SECURITY__SECRET_KEY`, `LOG__LEVEL`.
"""

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["local", "ci", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class DatabaseSettings(BaseModel):
    """PostgreSQL. Переменные с префиксом `DB__`."""

    url: str = Field(description="postgresql+asyncpg://user:pass@host:port/db")

    @field_validator("url")
    @classmethod
    def _require_async_driver(cls, value: str) -> str:
        """Синхронный драйвер подхватится и молча сломает весь async-слой."""
        if not value.startswith("postgresql+asyncpg://"):
            message = "DB__URL должен начинаться с postgresql+asyncpg://"
            raise ValueError(message)
        return value


class SecuritySettings(BaseModel):
    """Подписи и секреты. Переменные с префиксом `SECURITY__`."""

    secret_key: str = Field(
        min_length=32,
        description="Подпись JWT и токенов приглашений. Сгенерировать: openssl rand -hex 32",
    )


class AppSettings(BaseModel):
    """Поведение приложения наружу. Переменные с префиксом `APP__`."""

    environment: Environment = "local"
    public_url: str = Field(
        default="http://localhost:5173",
        description="Внешний адрес веб-клиента — база для ссылок в письмах",
    )
    # NoDecode: без него pydantic-settings пытается разобрать значение как JSON
    # прямо в источнике, и строка через запятую падает до валидатора.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Принимает и JSON-список, и строку через запятую — так удобнее в docker-compose."""
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                # JSONDecodeError — подкласс ValueError, pydantic покажет его как
                # обычную ошибку валидации с указанием поля.
                return json.loads(text)
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value


class LogSettings(BaseModel):
    """Логи. Переменные с префиксом `LOG__`."""

    level: LogLevel = "INFO"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    db: DatabaseSettings
    security: SecuritySettings
    app: AppSettings = Field(default_factory=AppSettings)
    log: LogSettings = Field(default_factory=LogSettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()
