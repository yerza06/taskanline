"""Сценарий Д: модель работает с трекером через MCP-сервер — в процессе и по HTTP.

Сервер ходит в приложение этого теста через SDK поверх ASGI: те же права, те же 404, та же
история изменений с токеном, что и в жизни.
"""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import httpx2
from fastapi import FastAPI
from httpx import AsyncClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy.ext.asyncio import AsyncSession

from taskanline_mcp.config import Settings
from taskanline_mcp.server import build
from tests.org import API
from tests.test_tasks import World

SignUp = Callable[..., Awaitable[AsyncClient]]


def settings(token: str | None, **changes: Any) -> Settings:
    base = {"api_url": "http://test", "token": token, "workspace": None, "web_url": "http://web"}
    return Settings(**{**base, **changes})


async def issue(client: AsyncClient, scope: str = "read_write") -> dict[str, Any]:
    response = await client.post(f"{API}/me/tokens", json={"name": "claude", "scope": scope})
    body: dict[str, Any] = response.json()
    return body


async def test_scenario_d_whats_in_progress_and_new_task(
    sign_up: SignUp, db_session: AsyncSession, app: FastAPI
) -> None:
    w = await World(sign_up, db_session).build()
    _, dev_id = await w.person(
        "dev@example.com", workspace_role="member", team_id=w.team["id"], team_role="member"
    )
    in_progress = w.states["In Progress"]["id"]
    await w.task(title="Редирект после логина", assignee_id=dev_id, state_id=in_progress)
    await w.task(title="Миграция биллинга", state_id=in_progress)
    await w.task(title="Ещё не начата")
    token = await issue(w.owner)
    server = build(settings(token["token"]), transport=lambda: httpx.ASGITransport(app=app))

    async with Client(server) as model:
        teams = await model.call_tool("list_teams", {})
        working = await model.call_tool("search_tasks", {"team": "ENG", "state_type": ["started"]})
        created = await model.call_tool(
            "create_task",
            {"title": "Обновить README", "team": "ENG", "assignee": "dev@example.com",
             "priority": "high"},
        )  # fmt: skip

    assert teams.structured_content is not None
    assert teams.structured_content["teams"][0]["key"] == "ENG"
    assert working.structured_content is not None
    assert [t["title"] for t in working.structured_content["tasks"]] == [
        "Редирект после логина",
        "Миграция биллинга",
    ]
    assert created.structured_content is not None
    new = created.structured_content["created"]
    assert (new["key"], new["assignee"], new["priority"]) == ("ENG-4", "dev@example.com", "high")
    assert new["url"] == "http://web/ENG-4"
    history = (await w.owner.get(f"{API}/tasks/ENG-4/activities")).json()["items"]
    assert history[-1]["type"] == "task_created"
    assert history[-1]["actor_token_id"] == token["id"]


async def test_read_only_refuses_clearly(
    sign_up: SignUp, db_session: AsyncSession, app: FastAPI
) -> None:
    w = await World(sign_up, db_session).build()
    await w.task(title="Задача")
    reader = await issue(w.owner, scope="read")
    transport: Callable[[], httpx.AsyncBaseTransport] = lambda: httpx.ASGITransport(app=app)  # noqa: E731

    async with Client(build(settings(reader["token"], read_only=True), transport=transport)) as m:
        names = {tool.name for tool in (await m.list_tools()).tools}
        refused = await m.call_tool("create_task", {"title": "x"})
    # Флаг забыли — токен со scope=read всё равно не даёт изменить.
    async with Client(build(settings(reader["token"]), transport=transport)) as m:
        denied = await m.call_tool("comment_task", {"key": "ENG-1", "body": "нельзя"})

    assert "create_task" not in names and "search_tasks" in names
    assert refused.is_error
    assert denied.is_error
    assert denied.content[0].text == "Токен выдан только на чтение. Изменения недоступны."  # type: ignore[union-attr]


async def test_streamable_http_takes_token_from_header(
    sign_up: SignUp, db_session: AsyncSession, app: FastAPI
) -> None:
    w = await World(sign_up, db_session).build()
    await w.task(title="Видна только владельцу токена")
    token = await issue(w.owner)
    server = build(
        settings(None, token_from_header=True), transport=lambda: httpx.ASGITransport(app=app)
    )
    mcp_app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=["mcp.test"]),
    )

    async def call(headers: dict[str, str]) -> Any:
        http = httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=mcp_app), base_url="http://mcp.test", headers=headers
        )
        async with (
            http,
            Client(streamable_http_client("http://mcp.test/mcp", http_client=http)) as m,
        ):
            return await m.call_tool("search_tasks", {})

    async with mcp_app.router.lifespan_context(mcp_app):
        anonymous = await call({})
        authorized = await call({"Authorization": f"Bearer {token['token']}"})

    assert anonymous.is_error
    assert "Authorization: Bearer" in anonymous.content[0].text
    assert [t["key"] for t in authorized.structured_content["tasks"]] == ["ENG-1"]
