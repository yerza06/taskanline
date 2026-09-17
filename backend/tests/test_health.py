from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app import __version__
from app.core import config, database


async def test_health_returns_ok_with_version(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__, "database": "ok"}


@pytest.fixture
def app_without_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    """Приложение, указывающее на заведомо недоступный PostgreSQL."""
    from app.main import create_app

    monkeypatch.setenv("DB__URL", "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/nowhere")
    config.get_settings.cache_clear()
    database.get_engine.cache_clear()
    try:
        yield create_app()
    finally:
        config.get_settings.cache_clear()
        database.get_engine.cache_clear()


async def test_health_reports_degraded_when_database_unavailable(
    app_without_database: FastAPI,
) -> None:
    transport = ASGITransport(app=app_without_database)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    # Движок закрывается здесь, в цикле теста: фикстура синхронная и сделать это
    # не может, а брошенное соединение asyncpg всплывает предупреждением при сборке мусора.
    await database.get_engine().dispose()

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"
