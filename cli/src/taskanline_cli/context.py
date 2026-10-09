"""Сессия команды: настройки, клиент SDK и перевод фильтров DSL в грамматику views.

Имена в id разрешает `Resolver` из SDK — общий с MCP-сервером; кэш у него на один вызов
`tkl`, повторный запрос списка статусов в его пределах ничего не даёт.

`RUNNER` и `TRANSPORT` — швы для тестов: первый исполняет корутину команды (по
умолчанию `asyncio.run`), второй подставляет транспорт httpx вместо сети.
"""

import asyncio
import os
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

import httpx

from taskanline_cli import config
from taskanline_cli.filters import Op, Term, date_value, priority_value
from taskanline_cli.output import Format, Result, choose_format, render
from taskanline_sdk import TasKanLineClient
from taskanline_sdk.models import Team
from taskanline_sdk.resolve import Resolver

RUNNER: Callable[[Coroutine[Any, Any, Any]], Any] = asyncio.run
TRANSPORT: Callable[[], httpx.AsyncBaseTransport | None] = lambda: None  # noqa: E731
# Дополнительные параметры клиента SDK — тесты выключают ими паузы между ретраями.
CLIENT_OPTIONS: dict[str, Any] = {}


class Options:
    """Глобальные опции — то, что корневой callback кладёт в `ctx.obj`."""

    def __init__(
        self,
        *,
        output: str | None = None,
        json_flag: bool = False,
        quiet: bool = False,
        no_color: bool = False,
        profile: str | None = None,
        api_url: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
        verbose: bool = False,
    ) -> None:
        self.output = output
        self.json_flag = json_flag
        self.quiet = quiet
        self.no_color = no_color
        self.profile = profile
        self.api_url = api_url
        self.token = token
        self.timeout = timeout
        self.verbose = verbose

    @property
    def format(self) -> Format:
        return choose_format(explicit=self.output, json_flag=self.json_flag, quiet=self.quiet)

    def settings(self, **overrides: Any) -> config.Settings:
        values = {"profile": self.profile, "api_url": self.api_url, "token": self.token}
        values.update({key: value for key, value in overrides.items() if value is not None})
        return config.resolve(timeout=self.timeout, **values)


# Опции текущего вызова. Не `click.get_current_context()`: Typer несёт свою копию Click,
# и контекст его команд глобальный стек настоящего Click не видит.
_current = Options()


def set_options(value: Options) -> None:
    global _current
    _current = value


def options() -> Options:
    return _current


class Session(Resolver):
    """Разрешение имён из SDK плюс настройки вызова и перевод фильтров DSL."""

    def __init__(self, settings: config.Settings, client: TasKanLineClient) -> None:
        super().__init__(client, workspace=settings.workspace, team=settings.team)
        self.settings = settings

    # --- Фильтры ------------------------------------------------------------------

    async def compile(self, terms: list[Term], team: Team | None) -> dict[str, Any]:
        """Термы DSL → фильтры грамматики views; имена — в id."""
        filters: dict[str, Any] = {}
        for term in terms:
            name, condition = await self._condition(term, team)
            filters[name] = condition
        if team is not None and "team_id" not in filters:
            filters["team_id"] = {"op": "in", "value": [str(team.id)]}
        return filters

    async def _condition(self, term: Term, team: Team | None) -> tuple[str, dict[str, Any]]:
        op, values = term.op, list(term.values)
        team_id = team.id if team else None

        def ids(found: list[Any]) -> dict[str, Any]:
            return {"op": op.value, "value": [str(item) for item in found]}

        match term.field:
            case "team":
                return "team_id", ids([(await self.team(v)).id for v in values])
            case "project":
                if op in (Op.IS_NULL, Op.NOT_NULL):
                    return "project_id", {"op": op.value}
                return "project_id", ids([(await self.project(v)).id for v in values])
            case "state":
                scope = [team] if team else await self.teams()
                return "state_id", ids(await self.state_ids(values, scope))
            case "state-type":
                return "state_type", {"op": op.value, "value": values}
            case "assignee" | "creator":
                field = "assignee_id" if term.field == "assignee" else "creator_id"
                if op in (Op.IS_NULL, Op.NOT_NULL):
                    return field, {"op": op.value}
                people = [
                    "@me" if v.lower() == "me" else str(await self.user_id(v)) for v in values
                ]
                return field, {"op": op.value, "value": people}
            case "label":
                return "label_id", ids(await self.label_ids(values, team_id))
            case "priority":
                numbers = [priority_value(v) for v in values]
                if op == Op.IN:
                    return "priority", {"op": "in", "value": numbers}
                if op == Op.NIN:
                    rest = [p for p in range(5) if p not in numbers]
                    return "priority", {"op": "in", "value": rest}
                return "priority", {"op": op.value, "value": numbers[0]}
            case "due" | "created" | "updated":
                field = {"due": "due_date", "created": "created_at", "updated": "updated_at"}[
                    term.field
                ]
                if op in (Op.IS_NULL, Op.NOT_NULL):
                    return field, {"op": op.value}
                return field, {
                    "op": "eq" if op == Op.IN else op.value,
                    "value": date_value(values[0]),
                }
            case "parent":
                if op in (Op.IS_NULL, Op.NOT_NULL):
                    return "has_parent", {"op": "eq", "value": op == Op.NOT_NULL}
                return "parent_id", ids([(await self.task(v)).id for v in values])
            case "title":
                return "title", {"op": "contains", "value": values[0]}
        raise AssertionError(term.field)


def run(action: Callable[[Session], Awaitable[Result | None]], **overrides: Any) -> None:
    """Исполнить команду: собрать настройки, открыть клиент, вывести результат."""
    opts = options()
    settings = opts.settings(**overrides)

    async def go() -> Result | None:
        async with TasKanLineClient(
            settings.api_url,
            settings.token,
            timeout=settings.timeout,
            transport=TRANSPORT(),
            **CLIENT_OPTIONS,
        ) as client:
            return await action(Session(settings, client))

    result = RUNNER(go())
    if result is not None:
        render(result, opts.format, color=not (opts.no_color or _no_color_env()))


def _no_color_env() -> bool:
    return bool(os.environ.get("NO_COLOR"))
