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
CookieSameSite = Literal["lax", "strict", "none"]
MailBackend = Literal["console", "smtp"]
MailSecurity = Literal["none", "starttls", "tls"]

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


class AuthSettings(BaseModel):
    """Сессии, cookie и защита от перебора. Переменные с префиксом `AUTH__`.

    Отдельно от `SECURITY__`: там лежит секрет, которым всё подписывается, здесь —
    политика, которую администратор инстанса правит, не трогая ключ.
    """

    access_ttl_minutes: int = Field(default=15, ge=1)
    refresh_ttl_days: int = Field(default=30, ge=1)
    # Secure не мешает локальной разработке: браузеры считают localhost доверенным
    # источником и принимают такие cookie по http.
    cookie_secure: bool = True
    cookie_samesite: CookieSameSite = "lax"
    # Пусто — cookie остаётся host-only. Домен нужен, только когда API и клиент
    # живут на разных поддоменах одного домена.
    cookie_domain: str = ""
    access_cookie_name: str = "tkl_access"
    refresh_cookie_name: str = "tkl_refresh"
    # Лимиты на перебор. Окно скользящее, счёт ведётся по адресу клиента.
    login_attempts: int = Field(default=10, ge=1)
    login_window_seconds: int = Field(default=60, ge=1)
    register_attempts: int = Field(default=5, ge=1)
    register_window_seconds: int = Field(default=3600, ge=1)


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


class MailSettings(BaseModel):
    """Исходящая почта. Переменные с префиксом `MAILER__`.

    Не `MAIL__`: эта переменная уже занята системой (`pam_mail`/Debian выставляют
    `MAIL=/var/spool/mail/<user>` при входе в shell), и `pydantic-settings` для
    вложенной модели отдаёт точному совпадению имени переменной приоритет перед
    разбором `__`-делимитера — `uv run pytest` в обычном терминале падал бы ещё
    до чтения `.env`.

    `console` пишет письмо в лог вместо отправки: на машине разработчика SMTP нет,
    а ссылку из приглашения всё равно нужно где-то увидеть.
    """

    backend: MailBackend = "console"
    host: str = "localhost"
    port: int = Field(default=587, ge=1, le=65535)
    username: str = ""
    password: SecretStr = SecretStr("")
    # starttls — порт 587, tls — порт 465, none — только для локального релея.
    security: MailSecurity = "starttls"
    from_address: str = "TasKanLine <noreply@localhost>"
    timeout_seconds: int = Field(default=10, ge=1)


class InvitationSettings(BaseModel):
    """Приглашения. Переменные с префиксом `INVITE__`.

    Срок жизни приглашения — в `instance_settings` (админ-панель): у одной величины
    не должно быть двух источников.
    """

    # Лимит на POST /invitations с одного адреса: приглашение — это письмо на чужой
    # ящик, и без лимита инстанс превращается в рассыльщик спама.
    attempts: int = Field(default=30, ge=1)
    window_seconds: int = Field(default=3600, ge=1)


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
    auth: AuthSettings = Field(default_factory=AuthSettings)
    app: AppSettings = Field(default_factory=AppSettings)
    cors: CorsSettings = Field(default_factory=CorsSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    log: LogSettings = Field(default_factory=LogSettings)
    mailer: MailSettings = Field(default_factory=MailSettings)
    invite: InvitationSettings = Field(default_factory=InvitationSettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()
