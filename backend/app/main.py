"""Сборка и запуск FastAPI-приложения.

Запускается как модуль: `python -m app.main`. Отдельная команда `uvicorn` для этого
не нужна — хост, порт и режим перезапуска уже описаны в настройках, и держать их
вторым списком в CMD контейнера значит однажды их рассинхронизировать.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app import __version__
from app.api import api_router
from app.core.config import get_settings
from app.core.csrf import CsrfMiddleware
from app.core.database import get_engine
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.mail import build_mailer
from app.core.middleware import RequestIdMiddleware
from app.core.rate_limit import InMemoryRateLimiter

logger = structlog.get_logger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["ok", "unavailable"]


async def _database_is_reachable() -> bool:
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as error:
        logger.warning("health.database_unavailable", error=type(error).__name__)
        return False
    return True


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    # До configure_logging(): она переустанавливает процессоры structlog, и лог,
    # отправленный после неё, тестовый `capture_logs` уже не увидит.
    if settings.app.environment == "production" and settings.mailer.backend == "console":
        logger.warning("mail.console_in_production")
    configure_logging(settings.log.level, json_output=settings.app.environment != "local")

    app = FastAPI(
        title="TasKanLine API",
        version=__version__,
        lifespan=lifespan,
    )
    # Лимитер привязан к приложению, а не к модулю: состояние окна не должно
    # переезжать между экземплярами приложения.
    app.state.rate_limiter = InMemoryRateLimiter()
    # Почтальон, как и лимитер, принадлежит приложению: тесты подменяют его своим.
    app.state.mailer = build_mailer(settings.mailer)
    app.add_middleware(CsrfMiddleware)
    # RequestIdMiddleware добавляется последним и потому отрабатывает первым:
    # отказ по CSRF должен попадать в лог с тем же request_id, что и запрос.
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.origins,
        allow_credentials=settings.cors.allow_credentials,
        allow_methods=settings.cors.allow_methods,
        allow_headers=settings.cors.allow_headers,
    )
    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/health", response_model=HealthResponse, tags=["service"])
    async def health() -> JSONResponse:
        """Готовность инстанса: версия приложения и доступность PostgreSQL."""
        reachable = await _database_is_reachable()
        payload = HealthResponse(
            status="ok" if reachable else "degraded",
            version=__version__,
            database="ok" if reachable else "unavailable",
        )
        return JSONResponse(status_code=200 if reachable else 503, content=payload.model_dump())

    return app


app = create_app()


def run() -> None:
    """Точка входа `python -m app.main`."""
    settings = get_settings()
    uvicorn.run(
        # Строкой, а не объектом: иначе не работает ни reload, ни запуск в несколько
        # воркеров — uvicorn импортирует приложение в каждом процессе сам.
        "app.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.reload,
        # Свой конфиг логов uvicorn не навязывает: формат уже задал structlog,
        # иначе одно и то же событие печатается дважды в двух разных форматах.
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    run()
