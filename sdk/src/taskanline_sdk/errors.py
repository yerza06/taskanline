"""Типизированные исключения SDK.

Ответ API с ошибкой несёт конверт `{"error": {"code", "message", "details"}}`; SDK
превращает его в исключение по статусу, сохраняя машиночитаемый `code` — по нему
ветвятся CLI и MCP-сервер, а не по тексту.
"""

from typing import Any


class TasKanLineError(Exception):
    """Общий предок всех ошибок SDK."""


class NetworkError(TasKanLineError):
    """Сервер недоступен или не ответил за отведённое время."""


class ApiError(TasKanLineError):
    """API ответило ошибкой. `code` — машиночитаемый код из конверта."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"[{code}] {message}")
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


class AuthenticationError(ApiError):
    """401: токена нет, он отозван или истёк."""


class PermissionDeniedError(ApiError):
    """403: объект виден, но действие запрещено ролью или scope токена."""


class NotFoundError(ApiError):
    """404: объекта нет — или он не виден этому пользователю."""


class ValidationError(ApiError):
    """400 и 422: запрос не прошёл проверку."""


class ConflictError(ApiError):
    """409: конфликт с текущим состоянием — занятый ключ, неоднозначная ссылка."""


class RateLimitError(ApiError):
    """429: превышен лимит. `retry_after` — сколько секунд подождать."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(status, code, message, details)
        self.retry_after = retry_after


class ServerError(ApiError):
    """5xx: ошибка на стороне сервера."""


_BY_STATUS: dict[int, type[ApiError]] = {
    400: ValidationError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: ValidationError,
}


def error_for(status: int, body: Any, *, retry_after: float | None = None) -> ApiError:
    """Исключение по статусу и телу ответа. Тело не по конверту — код `http_<status>`."""
    envelope = body.get("error") if isinstance(body, dict) else None
    if isinstance(envelope, dict):
        code = str(envelope.get("code") or f"http_{status}")
        message = str(envelope.get("message") or "")
        details = envelope.get("details") if isinstance(envelope.get("details"), dict) else {}
    else:
        code, message, details = f"http_{status}", f"HTTP {status}", {}
    if status == 429:
        return RateLimitError(status, code, message, details, retry_after=retry_after)
    if status >= 500:
        return ServerError(status, code, message, details)
    return _BY_STATUS.get(status, ApiError)(status, code, message, details)
