"""Общие фикстуры тестов.

Переменные окружения выставляются до импорта приложения: `Settings` читает их при
первом обращении, и подменять их позже уже поздно.
"""

import os
from pathlib import Path as _Path

from dotenv import dotenv_values

# Адрес тестовой базы ищем там же, где его держит разработчик: в окружении, затем
# в корневом .env. Иначе `uv run pytest` требует экспортировать переменную руками.
_ROOT = _Path(__file__).resolve().parents[2]
_DOTENV = dotenv_values(_ROOT / ".env") if (_ROOT / ".env").exists() else {}

TEST_DATABASE_URL = (
    os.environ.get("TEST_DATABASE_URL")
    or _DOTENV.get("TEST_DATABASE_URL")
    or "postgresql+asyncpg://taskanline:taskanline@localhost:5432/taskanline_test"
)
os.environ.setdefault("DB__URL", TEST_DATABASE_URL)
os.environ.setdefault("SECURITY__SECRET_KEY", "test-secret-key-at-least-32-characters-long")
os.environ.setdefault("APP__ENVIRONMENT", "ci")

import asyncio  # noqa: E402
from collections.abc import AsyncIterator, Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.database import get_engine, get_session  # noqa: E402
from app.main import create_app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Таблица-зонд существует только в тестовой базе: на ней проверяется, что фикстура
# действительно откатывает транзакцию между тестами.
PROBE_TABLE = "_isolation_probe"


def _dsn(url: str) -> str:
    """URL SQLAlchemy → DSN для asyncpg."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _create_database_if_missing() -> None:
    dsn = _dsn(TEST_DATABASE_URL)
    database = dsn.rsplit("/", 1)[-1]
    maintenance_dsn = dsn.rsplit("/", 1)[0] + "/postgres"

    connection = await asyncpg.connect(maintenance_dsn)
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", database)
        if not exists:
            await connection.execute(f'CREATE DATABASE "{database}"')
    finally:
        await connection.close()


@pytest.fixture(scope="session")
def migrated_database() -> None:
    """Один раз на прогон: создать базу, накатить миграции, добавить таблицу-зонд."""
    asyncio.run(_create_database_if_missing())

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(config, "head")

    async def _create_probe_table() -> None:
        connection = await asyncpg.connect(_dsn(TEST_DATABASE_URL))
        try:
            await connection.execute(f"CREATE TABLE IF NOT EXISTS {PROBE_TABLE} (value text)")
            await connection.execute(f"TRUNCATE {PROBE_TABLE}")
        finally:
            await connection.close()

    asyncio.run(_create_probe_table())


@pytest.fixture
async def db_connection(migrated_database: None) -> AsyncIterator[AsyncConnection]:
    """Соединение во внешней транзакции, которая откатывается после теста.

    Миграции затребованы через фикстуру, а не autouse: тестам настроек и чистых
    функций PostgreSQL не нужен, и они не должны падать вместе с ним.

    База между тестами не пересоздаётся — откат дешевле и не оставляет гонок.
    """
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    connection = await engine.connect()
    transaction = await connection.begin()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    """Сессия внутри той же транзакции: commit() в коде уходит в savepoint."""
    session = AsyncSession(
        bind=db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture(autouse=True)
async def close_engine_connections() -> AsyncIterator[None]:
    """Закрывает соединения движка приложения в том же цикле, где они открылись.

    Движок кэширован на весь прогон, а цикл событий у каждого теста свой: брошенное
    соединение asyncpg всплывает предупреждением «coroutine was never awaited»
    при сборке мусора.
    """
    yield
    await get_engine().dispose()


@pytest.fixture
def app(db_session: AsyncSession) -> Iterator[FastAPI]:
    application = create_app()

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_session] = _override_get_session
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
