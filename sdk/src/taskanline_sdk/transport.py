"""HTTP-уровень SDK: адрес, авторизация, ретраи и разбор ошибок.

Ретраи осторожные. 429 повторяется всегда — сервер отверг запрос, не исполняя его.
5xx и сетевой сбой повторяются только там, где повтор безопасен: у читающих и
идемпотентных методов и у запросов с `Idempotency-Key`. Иначе упавший на ответе
`POST` создал бы объект дважды.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx
from pydantic_core import to_jsonable_python

from taskanline_sdk._version import __version__
from taskanline_sdk.errors import NetworkError, RateLimitError, ServerError, error_for

API_PREFIX = "/api/v1"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
# Пауза растёт вдвое с каждой попыткой, но не дольше потолка.
MAX_BACKOFF = 30.0
# Retry-After дольше этого не ждём: агенту полезнее быстро получить 429 и решить самому.
MAX_RETRY_AFTER = 60.0

Sleep = Callable[[float], Awaitable[None]]


def api_root(base_url: str) -> str:
    """`https://host` и `https://host/api/v1` — один и тот же адрес API."""
    root = base_url.rstrip("/")
    return root if root.endswith(API_PREFIX) else root + API_PREFIX


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    try:
        return max(float(raw), 0.0) if raw is not None else None
    except ValueError:
        return None


def _clean(params: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Без `None`: отсутствующий фильтр не уходит строкой «None»."""
    if params is None:
        return None
    result: dict[str, Any] = {}
    for key, value in params.items():
        if value is None or value == []:
            continue
        if isinstance(value, bool):
            result[key] = "true" if value else "false"
        elif isinstance(value, list | tuple):
            result[key] = [str(to_jsonable_python(item)) for item in value]
        else:
            result[key] = str(to_jsonable_python(value))
    return result


class Transport:
    def __init__(
        self,
        base_url: str,
        token: str | None,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        headers = {"User-Agent": f"taskanline-sdk/{__version__}", "Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.AsyncClient(
            base_url=api_root(base_url), headers=headers, timeout=timeout, transport=transport
        )
        self._max_retries = max_retries
        self._backoff = backoff
        self._sleep = sleep

    @property
    def base_url(self) -> str:
        return str(self._http.base_url).rstrip("/")

    async def aclose(self) -> None:
        await self._http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Тело ответа как JSON (`None` для 204) или типизированное исключение."""
        method = method.upper()
        retry_unsafe = method in SAFE_METHODS or bool(headers and "Idempotency-Key" in headers)
        body = to_jsonable_python(json) if json is not None else None
        attempt = 0
        while True:
            try:
                response = await self._http.request(
                    method, path, params=_clean(params), json=body, headers=headers
                )
            except httpx.TimeoutException as error:
                failure: Exception = NetworkError(f"Сервер не ответил вовремя: {error}")
            except httpx.TransportError as error:
                failure = NetworkError(f"Сервер недоступен: {error}")
            else:
                if response.status_code < 400:
                    return response.json() if response.content else None
                failure = error_for(
                    response.status_code, _json(response), retry_after=_retry_after(response)
                )

            delay = self._delay(failure, attempt, retry_unsafe)
            if delay is None:
                raise failure
            await self._sleep(delay)
            attempt += 1

    def _delay(self, failure: Exception, attempt: int, retry_unsafe: bool) -> float | None:
        """Сколько ждать перед повтором; `None` — не повторять."""
        if attempt >= self._max_retries:
            return None
        backoff = min(self._backoff * float(2**attempt), MAX_BACKOFF)
        if isinstance(failure, RateLimitError):
            if failure.retry_after is None:
                return backoff
            return failure.retry_after if failure.retry_after <= MAX_RETRY_AFTER else None
        if isinstance(failure, ServerError | NetworkError) and retry_unsafe:
            return backoff
        return None


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None
