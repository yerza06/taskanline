"""Настройки приложения.

Единственный источник конфигурации: всё, что приходит извне, проходит через `Settings`
и проверяется при старте, а не в момент первого обращения где-то в глубине кода.

Настройки разложены по группам — по одной `BaseModel` на область ответственности.
Плоский список из двадцати полей к этапу 6 превращается в свалку, где `secret_key`
стоит рядом с `log_level` и ничто не подсказывает, что с чем связано. Группа заодно
задаёт префикс переменной окружения: `DB__HOST`, `SECURITY__SECRET_KEY`, `LOG__LEVEL`.
"""

import json
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import quote

from pydantic import BaseModel, Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["local", "ci", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Список через запятую или JSON-массив — оба варианта встречаются в compose и CI.
StringList = Annotated[list[str], NoDecode]


def _parse_string_list(value: object) -> object:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            # JSONDecodeError — подкласс ValueError, pydantic покажет его как
            # обычную ошибку валидации с указанием поля.
            return json.loads(text)
        return [item.strip() for item in text.split(",") if item.strip()]
    return value


class DatabaseSettings(BaseModel):
    """PostgreSQL. Переменные с префиксом `DB__`.

    Части хранятся по отдельности, а не одной строкой: в compose и в CI хост, пароль
    и имя базы приходят из разных мест, и склеивать их в URL приходилось бы руками —
    вместе с ручным экранированием пароля.
    """

    driver: str = "postgresql+asyncpg"
    user: str
    password: SecretStr
    host: str = "localhost"
    port: int = 5432
    name: str

    @field_validator("driver")
    @classmethod
    def _require_async_driver(cls, value: str) -> str:
        """Синхронный драйвер подхватится и молча сломает весь async-слой."""
        allowed = {"postgresql+asyncpg", "postgresql+psycopg"}
        if value not in allowed:
            message = f"DB__DRIVER должен быть async-драйвером: {', '.join(sorted(allowed))}"
            raise ValueError(message)
        return value

    @property
    def url(self) -> str:
        """Строка подключения для SQLAlchemy.

        Логин и пароль экранируются: двоеточие или собака в пароле иначе разваливают
        URL — `PostgresDsn.build` подставляет их как есть и падает на разборе.
        Не `computed_field`: иначе пароль попадёт в каждый `model_dump()`.
        """
        return str(
            PostgresDsn.build(
                scheme=self.driver,
                username=quote(self.user, safe=""),
                password=quote(self.password.get_secret_value(), safe=""),
                host=self.host,
                port=self.port,
                path=self.name,
            )
        )


class SecuritySettings(BaseModel):
    """Подписи и секреты. Переменные с префиксом `SECURITY__`."""

    secret_key: SecretStr = Field(
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


class CorsSettings(BaseModel):
    """Доступ из браузера. Переменные с префиксом `CORS__`.

    Политика целиком лежит здесь, а не наполовину в коде: разрешённые заголовки и
    методы различаются между локальной разработкой и продом, и правкой кода это
    решаться не должно.
    """

    origins: StringList = Field(default_factory=lambda: ["http://localhost:5173"])
    allow_credentials: bool = True
    allow_methods: StringList = Field(default_factory=lambda: ["*"])
    allow_headers: StringList = Field(default_factory=lambda: ["*"])

    _split = field_validator("origins", "allow_methods", "allow_headers", mode="before")(
        _parse_string_list
    )


class ServerSettings(BaseModel):
    """Где слушает uvicorn. Переменные с префиксом `SERVER__`."""

    # В контейнере слушать только loopback бессмысленно: наружу не достучаться.
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = Field(default=False, description="Автоперезапуск: только для разработки")


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
    cors: CorsSettings = Field(default_factory=CorsSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    log: LogSettings = Field(default_factory=LogSettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()
