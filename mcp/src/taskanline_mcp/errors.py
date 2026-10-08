"""Исключения SDK → текст для модели (MCP-спека §8).

Ошибка возвращается результатом инструмента с `isError`, а не исключением протокола:
модель читает текст и исправляется сама. Сообщение без подсказки, что делать дальше, —
плохое сообщение.
"""

from taskanline_sdk import (
    ApiError,
    AuthenticationError,
    NetworkError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    TasKanLineError,
)
from taskanline_sdk.resolve import ResolveError


class ToolInputError(ValueError):
    """Аргументы инструмента не сходятся между собой — модели нужно их поправить."""


def message_for(error: Exception) -> str:
    match error:
        case ToolInputError():
            return str(error)
        case ResolveError():
            return f"{error.message}. {error.hint}." if error.hint else f"{error.message}."
        case NetworkError():
            return "Сервер TasKanLine не отвечает. Проверьте TKL_API_URL и доступность сети."
        case AuthenticationError():
            return (
                "Токен не принят: он отозван, истёк или не передан. Проверьте TKL_TOKEN "
                "или заголовок Authorization: Bearer."
            )
        case PermissionDeniedError() if error.code == "insufficient_scope":
            return "Токен выдан только на чтение. Изменения недоступны."
        case PermissionDeniedError():
            return (
                "Недостаточно прав для этого действия. "
                "Обратитесь к администратору рабочего пространства."
            )
        case RateLimitError():
            wait = f"{error.retry_after:g}" if error.retry_after is not None else "несколько"
            return f"Превышен лимит запросов. Повторите через {wait} секунд."
        case ServerError():
            return f"Ошибка на сервере TasKanLine [{error.code}]. Повторите позже."
        case ApiError():
            details = "; ".join(f"{key}: {value}" for key, value in error.details.items())
            return f"{error.message or 'Запрос отклонён'} [{error.code}]" + (
                f". {details}" if details else ""
            )
        case TasKanLineError():
            return str(error)
    raise error
