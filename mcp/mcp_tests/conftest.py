"""Фикстуры MCP: сервер поверх поддельного API (того же, что у тестов CLI) и клиент в процессе."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp import Client

from cli_tests.fake_api import FakeApi
from taskanline_mcp.config import Settings
from taskanline_mcp.server import build

Connect = Callable[..., AbstractAsyncContextManager[Client]]


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()


@pytest.fixture
def connect(api: FakeApi, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Connect:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    @asynccontextmanager
    async def open_client(**overrides: Any) -> AsyncIterator[Client]:
        settings = Settings(
            **{
                "api_url": "http://tkl.test",
                "token": "tkl_test",
                "workspace": None,
                "web_url": "http://tkl.test",
                **overrides,
            }
        )
        server = build(
            settings,
            transport=lambda: httpx.MockTransport(api.handle),
            client_options={"max_retries": 0},
        )
        async with Client(server) as client:
            yield client

    return open_client
