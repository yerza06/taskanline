"""Сессия команды: настройки, клиент SDK и разрешение имён в id.

Агент пишет `team:ENG`, `state:"In Progress"`, `assignee:dev@example.com`, а API ждёт
UUID. Всё разрешение — здесь, с кэшем на одну команду: `tkl` живёт один вызов, и
повторный запрос списка статусов в его пределах ничего не даёт.

`RUNNER` и `TRANSPORT` — швы для тестов: первый исполняет корутину команды (по
умолчанию `asyncio.run`), второй подставляет транспорт httpx вместо сети.
"""

import asyncio
import difflib
import os
import re
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any
from uuid import UUID

import httpx

from taskanline_cli import config
from taskanline_cli.errors import CliError, ExitCode, not_found, usage
from taskanline_cli.filters import Op, Term, date_value, priority_value
from taskanline_cli.output import Format, Result, choose_format, render
from taskanline_sdk import NotFoundError, TasKanLineClient
from taskanline_sdk.models import Label, Me, Member, Project, State, Task, Team, View, Workspace

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


TASK_KEY = re.compile(r"[A-Za-z]{2,5}-\d+")

# Опции текущего вызова. Не `click.get_current_context()`: Typer несёт свою копию Click,
# и контекст его команд глобальный стек настоящего Click не видит.
_current = Options()


def set_options(value: Options) -> None:
    global _current
    _current = value


def options() -> Options:
    return _current


def _uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _names(items: list[str]) -> str:
    return ", ".join(items) if items else "нет ни одного"


class Session:
    def __init__(self, settings: config.Settings, client: TasKanLineClient) -> None:
        self.settings = settings
        self.client = client
        self._me: Me | None = None
        self._workspace: Workspace | None = None
        self._teams: list[Team] | None = None
        self._states: dict[UUID, list[State]] = {}
        self._labels: list[Label] | None = None
        self._members: list[Member] | None = None
        self._projects: list[Project] | None = None

    # --- Кто я и где я ------------------------------------------------------------

    async def me(self) -> Me:
        if self._me is None:
            self._me = await self.client.me.get()
        return self._me

    async def workspace(self, ref: str | None = None) -> Workspace:
        """Workspace из `--workspace`, профиля или единственный доступный."""
        if ref is None and self._workspace is not None:
            return self._workspace
        wanted = ref or self.settings.workspace
        spaces = await self.client.workspaces.all()
        if wanted is None:
            if len(spaces) == 1:
                self._workspace = spaces[0]
                return spaces[0]
            raise usage(
                "workspace_required",
                "Не выбран workspace",
                f"Укажите --workspace или tkl config set workspace SLUG. "
                f"Доступные: {_names([space.slug for space in spaces])}",
            )
        for space in spaces:
            if wanted in (space.slug, str(space.id)):
                if ref is None:
                    self._workspace = space
                return space
        raise not_found(
            "workspace_not_found",
            f"Workspace «{wanted}» не найден",
            f"Доступные: {_names([space.slug for space in spaces])}. Список — tkl ws list",
        )

    async def teams(self) -> list[Team]:
        if self._teams is None:
            self._teams = await self.client.teams.all((await self.workspace()).id)
        return self._teams

    async def team(self, ref: str) -> Team:
        teams = await self.teams()
        for team in teams:
            if ref.upper() == team.key or ref == str(team.id):
                return team
        raise not_found(
            "team_not_found",
            f"Команда «{ref}» не найдена",
            f"Доступные команды: {_names([team.key for team in teams])}. Список — tkl team list",
        )

    async def default_team(self, explicit: str | None, *, all_teams: bool = False) -> Team | None:
        """`--team` → команда из профиля → нет; `--all-teams` снимает команду профиля."""
        if explicit:
            return await self.team(explicit)
        if all_teams or not self.settings.team:
            return None
        return await self.team(self.settings.team)

    async def require_team(self, explicit: str | None) -> Team:
        team = await self.default_team(explicit)
        if team is None:
            teams = await self.teams()
            if len(teams) == 1:
                return teams[0]
            raise usage(
                "team_required",
                "Не выбрана команда",
                f"Укажите --team или tkl config set team KEY. "
                f"Доступные: {_names([team.key for team in teams])}",
            )
        return team

    async def states(self, team_id: UUID) -> list[State]:
        if team_id not in self._states:
            self._states[team_id] = await self.client.teams.states(team_id)
        return self._states[team_id]

    async def state(self, team_id: UUID, name: str) -> State:
        states = await self.states(team_id)
        for state in states:
            if state.name.casefold() == name.casefold() or str(state.id) == name:
                return state
        names = [state.name for state in states]
        close = difflib.get_close_matches(name, names, n=1)
        raise not_found(
            "state_not_found",
            f"Статус «{name}» не найден",
            (f"Возможно: {close[0]}. " if close else "")
            + f"Статусы команды: {_names(names)}. Список — tkl team states",
        )

    async def labels(self) -> list[Label]:
        if self._labels is None:
            self._labels = await self.client.labels.all((await self.workspace()).id)
        return self._labels

    async def label_ids(self, names: list[str], team_id: UUID | None = None) -> list[UUID]:
        """Метки по имени; одноимённые у команды и у workspace — обе."""
        labels = [
            label
            for label in await self.labels()
            if team_id is None or label.team_id in (None, team_id)
        ]
        ids: list[UUID] = []
        for name in names:
            found = [
                label.id
                for label in labels
                if label.name.casefold() == name.casefold() or str(label.id) == name
            ]
            if not found:
                raise not_found(
                    "label_not_found",
                    f"Метка «{name}» не найдена",
                    f"Доступные: {_names(sorted({label.name for label in labels}))}",
                )
            ids.extend(found)
        return ids

    async def members(self) -> list[Member]:
        if self._members is None:
            self._members = await self.client.workspaces.members((await self.workspace()).id)
        return self._members

    async def user_id(self, ref: str) -> UUID:
        """`me`, email участника workspace или UUID."""
        if ref.lower() == "me":
            return (await self.me()).id
        if (value := _uuid(ref)) is not None:
            return value
        for member in await self.members():
            if member.email.casefold() == ref.casefold():
                return member.user_id
        raise not_found(
            "user_not_found",
            f"Участник «{ref}» не найден в workspace",
            "Список участников — tkl ws members",
        )

    async def projects(self) -> list[Project]:
        if self._projects is None:
            found: list[Project] = []
            for team in await self.teams():
                found.extend(await self.client.projects.all(team.id))
            self._projects = found
        return self._projects

    async def project(self, ref: str) -> Project:
        if (value := _uuid(ref)) is not None:
            return await self.client.projects.get(value)
        matches = [p for p in await self.projects() if p.name.casefold() == ref.casefold()]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise CliError(
                ExitCode.CONFLICT,
                "project_ambiguous",
                f"Проектов «{ref}» несколько",
                "Укажите id проекта: tkl project list",
            )
        raise not_found("project_not_found", f"Проект «{ref}» не найден", "tkl project list")

    async def task(self, ref: str, *, expand: tuple[str, ...] = ()) -> Task:
        """Задача по ключу или UUID; ненайденная — с подсказкой, какие команды есть."""
        if TASK_KEY.fullmatch(ref):
            ref = ref.upper()
        try:
            return await self.client.tasks.get(ref, expand=expand)
        except NotFoundError as error:
            hint = None
            try:
                keys = [team.key for team in await self.teams()]
                hint = f"Доступные команды: {_names(keys)}. Проверьте ключ или tkl task list"
            except CliError:
                pass
            raise not_found(error.code, f"Задача {ref.upper()} не найдена", hint) from error

    async def view(self, ref: str) -> View:
        """View по id или имени среди видимых."""
        if (value := _uuid(ref)) is not None:
            return await self.client.views.get(value)
        views = await self.client.views.all((await self.workspace()).id)
        matches = [view for view in views if view.name.casefold() == ref.casefold()]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise CliError(
                ExitCode.CONFLICT,
                "view_ambiguous",
                f"Views с именем «{ref}» несколько",
                "Укажите id: tkl view list",
            )
        raise not_found(
            "view_not_found",
            f"View «{ref}» не найден",
            f"Доступные: {_names([view.name for view in views])}",
        )

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
                found = []
                for value in values:
                    matched = [
                        state.id
                        for candidate in scope
                        for state in await self.states(candidate.id)
                        if state.name.casefold() == value.casefold()
                    ]
                    if not matched:
                        known = sorted({s.name for c in scope for s in await self.states(c.id)})
                        close = difflib.get_close_matches(value, known, n=1)
                        raise not_found(
                            "state_not_found",
                            f"Статус «{value}» не найден",
                            (f"Возможно: {close[0]}. " if close else "")
                            + f"Статусы: {_names(known)}. Список — tkl team states KEY",
                        )
                    found.extend(matched)
                return "state_id", ids(found)
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
