"""Сборка FastAPI-приложения."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app import __version__
from app.core.config import get_settings
from app.core.database import get_engine
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware

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
    configure_logging(settings.log.level, json_output=settings.app.environment != "local")

    app = FastAPI(
        title="TasKanLine API",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)

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
