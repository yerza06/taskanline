"""Сценарий Г: агент работает с задачами только через `tkl`.

CLI вызывается так же, как из терминала, — `main(argv)`, — но ходит не в сеть, а в
приложение этого теста поверх ASGI. Команда исполняется в отдельном потоке: она
синхронная, а её корутина уходит в цикл событий теста, где живёт соединение с базой.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from taskanline_cli import context
from taskanline_cli.app import main
from tests.org import API
from tests.test_tasks import World

SignUp = Callable[..., Awaitable[AsyncClient]]


@dataclass
class Run:
    code: int
    out: str
    err: str

    def json(self) -> Any:
        return json.loads(self.out)


def _without_server_logs(out: str) -> str:
    """Приложение пишет журнал запросов в тот же stdout, что и CLI в этом процессе.

    В жизни сервер — другой процесс; здесь его строки (JSON с `event`) отбрасываются.
    """
    kept = []
    for line in out.splitlines(keepends=True):
        try:
            record = json.loads(line)
        except ValueError:
            record = None
        if not (isinstance(record, dict) and "event" in record and "level" in record):
            kept.append(line)
    return "".join(kept)


@pytest.fixture
async def tkl(
    app: FastAPI,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Callable[..., Awaitable[Run]]:
    loop = asyncio.get_running_loop()

    def on_test_loop(coroutine: Coroutine[Any, Any, Any]) -> Any:
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result()

    monkeypatch.setattr(context, "RUNNER", on_test_loop)
    monkeypatch.setattr(context, "TRANSPORT", lambda: httpx.ASGITransport(app=app))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("TKL_API_URL", "http://test")
    for name in ("TKL_TOKEN", "TKL_PROFILE", "TKL_WORKSPACE", "TKL_TEAM", "TKL_OUTPUT"):
        monkeypatch.delenv(name, raising=False)

    async def invoke(*args: str) -> Run:
        capsys.readouterr()
        code = await asyncio.to_thread(main, list(args))
        captured = capsys.readouterr()
        return Run(code, _without_server_logs(captured.out), captured.err)

    return invoke


async def test_scenario_g_agent_works_through_cli(
    sign_up: SignUp, db_session: AsyncSession, tkl: Callable[..., Awaitable[Run]]
) -> None:
    w = await World(sign_up, db_session).build()
    agent, agent_id = await w.person(
        "agent@example.com", workspace_role="member", team_id=w.team["id"], team_role="member"
    )
    issued = (
        await agent.post(f"{API}/me/tokens", json={"name": "claude-code", "scope": "read_write"})
    ).json()
    await w.task(title="Чужая")  # ENG-1
    await w.task(title="Починить редирект", assignee_id=agent_id, priority=2)  # ENG-2
    await w.task(title="Уже в работе", assignee_id=agent_id, state_id=w.states["In Progress"]["id"])

    login = await tkl("auth", "login", "--token", issued["token"])
    mine = await tkl("task", "list", "--filter", "assignee:me state-type:unstarted", "--json")
    states = await tkl("team", "states", "ENG")
    taken = await tkl("task", "update", "ENG-2", "--state", "In Progress")
    commented = await tkl("task", "comment", "eng-2", "-m", "Причина — потеря query. PR #218.")
    closed = await tkl("task", "close", "ENG-2")
    missing = await tkl("task", "show", "ENG-999")

    assert login.code == 0, login.err
    assert [task["key"] for task in mine.json()["items"]] == ["ENG-2"]
    assert mine.json()["items"][0]["url"].endswith("/ENG-2")
    assert [state["name"] for state in states.json()["items"]][:3] == [
        "Backlog",
        "Todo",
        "In Progress",
    ]
    assert taken.json()["state"] == {"name": "In Progress", "type": "started"}
    assert commented.code == 0, commented.err
    assert closed.json()["state"]["type"] == "completed"
    assert (missing.code, missing.out) == (4, "")
    assert "Доступные команды: ENG" in missing.err

    history = (await w.owner.get(f"{API}/tasks/ENG-2/activities")).json()["items"]
    by_agent = [item for item in history if item["actor_token_id"] == issued["id"]]
    assert {item["type"] for item in by_agent} >= {"state_changed", "commented"}


async def test_read_token_cannot_change_anything(
    sign_up: SignUp, db_session: AsyncSession, tkl: Callable[..., Awaitable[Run]]
) -> None:
    w = await World(sign_up, db_session).build()
    await w.task(title="Задача")
    token = (await w.owner.post(f"{API}/me/tokens", json={"name": "reader"})).json()["token"]

    listed = await tkl("--token", token, "task", "list")
    denied = await tkl("--token", token, "task", "comment", "ENG-1", "-m", "нельзя")

    assert listed.code == 0, listed.err
    assert listed.json()["total_hint"] == 1
    assert denied.code == 3
    assert "[insufficient_scope]" in denied.err


async def test_views_by_name(
    sign_up: SignUp, db_session: AsyncSession, tkl: Callable[..., Awaitable[Run]]
) -> None:
    w = await World(sign_up, db_session).build()
    await w.task(title="Срочная", priority=1)
    await w.task(title="Низкая", priority=4)
    token = (
        await w.owner.post(f"{API}/me/tokens", json={"name": "agent", "scope": "read_write"})
    ).json()["token"]
    await tkl("auth", "login", "--token", token)

    created = await tkl(
        "view", "create", "--name", "Срочное", "--filter", "priority:<=2", "--group-by", "priority"
    )
    ran = await tkl("view", "run", "срочное")

    assert created.code == 0, created.err
    assert created.json()["filters"] == {"priority": {"op": "lte", "value": 2}}
    assert ran.json()["groups"] == [
        {"key": "1", "name": "urgent", "count": 1, "next_cursor": None, "has_more": False}
    ]
    assert [(t["key"], t["group"]) for t in ran.json()["items"]] == [("ENG-1", "urgent")]
