"""Перечисления, дублирующие ограничения `CHECK` в базе.

В схеме это `VARCHAR` с `CHECK`, а не нативный enum PostgreSQL: добавление значения
в нативный enum — миграция с блокировкой, правка `CHECK` — нет. Расплата за это —
список значений в двух местах, и здесь его питоновская половина.
"""

from enum import StrEnum


class InstanceRole(StrEnum):
    """Роль на уровне сервера — ось, независимая от ролей внутри workspace."""

    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    SUPPORT = "support"
    USER = "user"


class TokenScope(StrEnum):
    """Что разрешено токену агента."""

    READ = "read"
    READ_WRITE = "read_write"


class AuthMethod(StrEnum):
    """Чем доказана личность: cookie-сессией человека или токеном агента."""

    SESSION = "session"
    TOKEN = "token"
