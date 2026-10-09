import os
from pathlib import Path as _Path

from dotenv import dotenv_values

# Параметры подключения берём там же, где их держит разработчик: окружение, затем
# корневой .env, затем разумные значения по умолчанию. Имя базы всегда своё —
# гонять тесты по рабочей базе нельзя даже случайно.
_ROOT = _Path(__file__).resolve().parents[2]
_DOTENV = dotenv_values(_ROOT / ".env") if (_ROOT / ".env").exists() else {}

_DB_DEFAULTS = {
    "DB__USER": "taskanline",
    "DB__PASSWORD": "taskanline",
    "DB__HOST": "localhost",
    "DB__PORT": "5432",
}

for _key, _fallback in _DB_DEFAULTS.items():
    os.environ.setdefault(_key, _DOTENV.get(_key) or _fallback)

os.environ["DB__NAME"] = (
    os.environ.get("TEST_DB_NAME") or _DOTENV.get("TEST_DB_NAME") or "taskanline_test"
)
os.environ.setdefault("SECURITY__SECRET_KEY", "test-secret-key-at-least-32-characters-long")
# Не setdefault: `local` из окружения разработчика включил бы цветной журнал, а тесты CLI
# отделяют строки сервера от вывода команды по JSON. Тесты режимов ставят своё значение сами.
os.environ["APP__ENVIRONMENT"] = "ci"
# Тестовый клиент ходит по http, а Secure-cookie по нему не отправляется.
# В продакшене флаг обязан быть включён — здесь он мешал бы проверять сессию.
os.environ["AUTH__COOKIE_SECURE"] = "false"

import asyncio  # noqa: E402
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import get_engine, get_session  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.org import RecordingMailer  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Тот же URL, что соберёт приложение: одна дорога до базы, а не две расходящиеся.
TEST_DATABASE_URL = get_settings().db.url

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
    # Миграция закрывает регистрацию (`invite_only`), а тесты заводят людей через
    # `sign_up`. Открываем её в транзакции теста; проверки режимов меняют его сами.
    await db_connection.execute(
        text("UPDATE instance_settings SET registration_mode = 'open' WHERE id = 1")
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
def mailer() -> RecordingMailer:
    return RecordingMailer()


@pytest.fixture
def app(db_session: AsyncSession, mailer: RecordingMailer) -> Iterator[FastAPI]:
    application = create_app()
    application.state.mailer = mailer

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


CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
async def new_client(app: FastAPI) -> AsyncIterator[Callable[[], AsyncClient]]:
    """Фабрика клиентов: у каждого свои cookie и свой адрес.

    Свой адрес — ради лимитов: окно регистрации считается по IP, и пятый
    пользователь в одном тесте иначе получил бы 429.
    """
    clients: list[AsyncClient] = []

    def _new() -> AsyncClient:
        transport = ASGITransport(app=app, client=(f"10.0.0.{len(clients) + 1}", 50000))
        client = AsyncClient(transport=transport, base_url="http://test", headers=CSRF_HEADERS)
        clients.append(client)
        return client

    yield _new
    for client in clients:
        await client.aclose()


@pytest.fixture
def sign_up(new_client: Callable[[], AsyncClient]) -> Callable[..., Awaitable[AsyncClient]]:
    """Зарегистрированный пользователь со своей cookie-сессией."""

    async def _sign_up(email: str, full_name: str = "Участник") -> AsyncClient:
        client = new_client()
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "correct horse battery", "full_name": full_name},
        )
        assert response.status_code == 201, response.text
        return client

    return _sign_up


@pytest.fixture
async def session_client(client: AsyncClient) -> AsyncClient:
    """Клиент с открытой cookie-сессией зарегистрированного пользователя.

    Пользователь единственный, поэтому его роль инстанса — superadmin.
    """
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "ivan@example.com",
            "password": "correct horse battery",
            "full_name": "Иван Иванов",
        },
        headers=CSRF_HEADERS,
    )
    assert response.status_code == 201, response.text
    return client


@pytest.fixture
async def issue_token(session_client: AsyncClient) -> Callable[[str], Awaitable[str]]:
    """Фабрика токенов агента: `await issue_token("read")` отдаёт полный токен."""

    async def _issue(scope: str = "read_write", name: str = "agent") -> str:
        response = await session_client.post(
            "/api/v1/me/tokens",
            json={"name": name, "scope": scope},
            headers=CSRF_HEADERS,
        )
        assert response.status_code == 201, response.text
        token: str = response.json()["token"]
        return token

    return _issue
