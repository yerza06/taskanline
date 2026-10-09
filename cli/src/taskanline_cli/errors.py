"""Коды выхода и текст ошибок (CLI-спека §8).

Раздельные коды нужны агенту: по 4 он уточняет идентификатор, по 3 — просит доступ у
человека, по 6 — ждёт. Ошибка в stderr всегда несёт машиночитаемый код API.
"""

from enum import IntEnum

from taskanline_sdk import (
    ApiError,
    AuthenticationError,
    ConflictError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    TasKanLineError,
)


class ExitCode(IntEnum):
    OK = 0
    USAGE = 1
    API = 2
    ACCESS = 3
    NOT_FOUND = 4
    CONFLICT = 5
    RATE_LIMIT = 6
    NETWORK = 7


class CliError(Exception):
    """Ошибка, обнаруженная самим CLI: неизвестный статус, нет контекста workspace, …

    `code` — того же вида, что коды API, чтобы агент разбирал их одинаково.
    """

    def __init__(
        self, exit_code: ExitCode, code: str, message: str, hint: str | None = None
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.code = code
        self.message = message
        self.hint = hint


def usage(code: str, message: str, hint: str | None = None) -> CliError:
    return CliError(ExitCode.USAGE, code, message, hint)


def not_found(code: str, message: str, hint: str | None = None) -> CliError:
    return CliError(ExitCode.NOT_FOUND, code, message, hint)


def exit_code_for(error: TasKanLineError) -> ExitCode:
    match error:
        case NetworkError():
            return ExitCode.NETWORK
        case AuthenticationError() | PermissionDeniedError():
            return ExitCode.ACCESS
        case NotFoundError():
            return ExitCode.NOT_FOUND
        case ConflictError():
            return ExitCode.CONFLICT
        case RateLimitError():
            return ExitCode.RATE_LIMIT
    return ExitCode.API


def describe(error: TasKanLineError) -> str:
    """Текст для stderr: код, сообщение и, где есть, что делать дальше."""
    if isinstance(error, NetworkError):
        return f"Ошибка [network_error]: {error}"
    assert isinstance(error, ApiError)
    lines = [f"Ошибка [{error.code}]: {error.message or 'без описания'}"]
    if isinstance(error, RateLimitError) and error.retry_after is not None:
        lines.append(f"Повторите через {error.retry_after:g} с (Retry-After).")
    if error.code == "insufficient_scope":
        lines.append("Токен выдан только на чтение — для изменений нужен токен read_write.")
    elif error.code == "insufficient_role":
        required = error.details.get("required")
        lines.append(
            f"Нужна роль {required} — попросите её у администратора."
            if required
            else "Недостаточно прав — попросите доступ у администратора."
        )
    elif isinstance(error, AuthenticationError):
        lines.append("Проверьте токен: tkl auth status, новый — tkl auth login --token …")
    for key, value in error.details.items():
        if key not in ("required",):
            lines.append(f"  {key}: {value}")
    return "\n".join(lines)
