"""Защита от подделки межсайтового запроса.

`SameSite=Lax` отсекает основную массу атак, но не все: заголовок `X-Requested-With`
добавляет вторую проверку, которую сторонняя страница не может пройти — простыми
формами и картинками произвольный заголовок не выставить, а fetch с ним требует
успешного preflight, и CORS его не разрешит.

Проверка нужна только там, где браузер прикладывает учётные данные сам. Запрос с
`Authorization` под неё не попадает: подставить заголовок со стороннего сайта
нечем, и агент, ходящий токеном, к CSRF отношения не имеет.

Реализовано middleware, а не зависимостью: зависимость можно забыть повесить на
новый эндпоинт, middleware — нет.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.errors import error_response

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
REQUIRED_HEADER = "x-requested-with"
REQUIRED_VALUE = "XMLHttpRequest"


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if self._needs_header(request) and request.headers.get(REQUIRED_HEADER) != REQUIRED_VALUE:
            return error_response(
                403,
                "csrf_required",
                f"Мутирующий запрос с cookie-сессией требует заголовка {REQUIRED_VALUE}",
                {"header": "X-Requested-With"},
            )
        return await call_next(request)

    @staticmethod
    def _needs_header(request: Request) -> bool:
        if request.method not in MUTATING_METHODS:
            return False
        if request.headers.get("authorization"):
            return False

        settings = get_settings()
        return any(
            name in request.cookies
            for name in (settings.auth.access_cookie_name, settings.auth.refresh_cookie_name)
        )
