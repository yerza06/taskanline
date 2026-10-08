"""Разрешение человеческих имён в id: ключ команды, имя статуса, метки, email, ключ задачи.

Агент пишет `ENG`, `"In Progress"`, `dev@example.com`, а API ждёт UUID. Этим пользуются и
CLI, и MCP-сервер — поэтому разрешение живёт в SDK, а не в каждом из них. Кэш — на время
жизни `Resolver`: один вызов CLI или один вызов инструмента MCP.

Ошибка разрешения — `ResolveError` с подсказкой, из которой видно, что выбрать вместо:
модель или агент должны исправиться сами, не спрашивая человека.
"""

import contextlib
import difflib
import re
from typing import Literal
from uuid import UUID

from taskanline_sdk.client import TasKanLineClient
from taskanline_sdk.errors import NotFoundError, TasKanLineError
from taskanline_sdk.models import Label, Me, Member, Project, State, Task, Team, View, Workspace

TASK_KEY = re.compile(r"[A-Za-z]{2,5}-\d+")
ResolveKind = Literal["not_found", "ambiguous", "required"]


class ResolveError(TasKanLineError):
    """Имя не разрешилось: нет такого (`not_found`), несколько (`ambiguous`) или не выбрано,
    а выбрать самому нельзя (`required`). `code` — в стиле кодов API."""

    def __init__(self, kind: ResolveKind, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message if hint is None else f"{message}. {hint}")
        self.kind = kind
        self.code = code
        self.message = message
        self.hint = hint


def _uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def names(items: list[str]) -> str:
    return ", ".join(items) if items else "нет ни одного"


def _close(value: str, options: list[str]) -> str:
    close = difflib.get_close_matches(value, options, n=1)
    return f"Возможно: {close[0]}. " if close else ""


class Resolver:
    """`workspace` — slug или id по умолчанию; `restrict` запрещает выходить за него
    (MCP-сервер с `--workspace` не показывает другие пространства вовсе)."""

    def __init__(
        self,
        client: TasKanLineClient,
        *,
        workspace: str | None = None,
        team: str | None = None,
        restrict: bool = False,
    ) -> None:
        self.client = client
        self.default_workspace = workspace
        self.default_team_ref = team
        self.restrict = restrict and workspace is not None
        self._me: Me | None = None
        self._spaces: list[Workspace] | None = None
        self._workspace: Workspace | None = None
        self._teams: list[Team] | None = None
        self._states: dict[UUID, list[State]] = {}
        self._labels: list[Label] | None = None
        self._members: list[Member] | None = None
        self._projects: list[Project] | None = None

    # --- Кто я и где я ----------------------------------------------------------------

    async def me(self) -> Me:
        if self._me is None:
            self._me = await self.client.me.get()
        return self._me

    async def workspaces(self) -> list[Workspace]:
        """Доступные пространства; при `restrict` — только заданное."""
        if self._spaces is None:
            spaces = await self.client.workspaces.all()
            if self.restrict:
                spaces = [s for s in spaces if self.default_workspace in (s.slug, str(s.id))]
            self._spaces = spaces
        return self._spaces

    async def workspace(self, ref: str | None = None) -> Workspace:
        """Названный, заданный по умолчанию или единственный доступный workspace."""
        if ref is None and self._workspace is not None:
            return self._workspace
        wanted = ref or self.default_workspace
        spaces = await self.workspaces()
        slugs = [space.slug for space in spaces]
        if wanted is None:
            if len(spaces) == 1:
                self._workspace = spaces[0]
                return spaces[0]
            raise ResolveError(
                "required",
                "workspace_required",
                "Не выбран workspace",
                f"Доступные: {names(slugs)}",
            )
        for space in spaces:
            if wanted in (space.slug, str(space.id)):
                if ref is None:
                    self._workspace = space
                return space
        raise ResolveError(
            "not_found",
            "workspace_not_found",
            f"Workspace «{wanted}» не найден",
            f"Доступные: {names(slugs)}",
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
        raise ResolveError(
            "not_found",
            "team_not_found",
            f"Команда «{ref}» не найдена",
            f"Доступные команды: {names([team.key for team in teams])}",
        )

    async def default_team(self, explicit: str | None, *, all_teams: bool = False) -> Team | None:
        """Названная → заданная по умолчанию → нет; `all_teams` снимает команду по умолчанию."""
        if explicit:
            return await self.team(explicit)
        if all_teams or not self.default_team_ref:
            return None
        return await self.team(self.default_team_ref)

    async def require_team(self, explicit: str | None) -> Team:
        """Как `default_team`, но команда нужна: единственную берём сами, иначе — ошибка."""
        team = await self.default_team(explicit)
        if team is not None:
            return team
        teams = await self.teams()
        if len(teams) == 1:
            return teams[0]
        raise ResolveError(
            "required",
            "team_required",
            "Не выбрана команда",
            f"Доступные команды: {names([team.key for team in teams])}",
        )

    # --- Статусы, метки, люди ---------------------------------------------------------

    async def states(self, team_id: UUID) -> list[State]:
        if team_id not in self._states:
            self._states[team_id] = await self.client.teams.states(team_id)
        return self._states[team_id]

    async def state(self, team_id: UUID, name: str) -> State:
        states = await self.states(team_id)
        for state in states:
            if state.name.casefold() == name.casefold() or str(state.id) == name:
                return state
        known = [state.name for state in states]
        key = None
        with contextlib.suppress(TasKanLineError):
            key = next((t.key for t in await self.teams() if t.id == team_id), None)
        where = f" в команде {key}" if key else ""
        raise ResolveError(
            "not_found",
            "state_not_found",
            f"Статус «{name}» не существует{where}",
            _close(name, known) + f"Доступные: {names(known)}",
        )

    async def state_ids(self, wanted: list[str], teams: list[Team]) -> list[UUID]:
        """Статусы по имени во всех названных командах: «Done» у ENG и у DES — оба."""
        found: list[UUID] = []
        for name in wanted:
            matched = [
                state.id
                for team in teams
                for state in await self.states(team.id)
                if state.name.casefold() == name.casefold()
            ]
            if not matched:
                known = sorted({s.name for team in teams for s in await self.states(team.id)})
                raise ResolveError(
                    "not_found",
                    "state_not_found",
                    f"Статус «{name}» не найден",
                    _close(name, known) + f"Доступные: {names(known)}",
                )
            found.extend(matched)
        return found

    async def labels(self) -> list[Label]:
        if self._labels is None:
            self._labels = await self.client.labels.all((await self.workspace()).id)
        return self._labels

    async def label_ids(self, wanted: list[str], team_id: UUID | None = None) -> list[UUID]:
        """Метки по имени; одноимённые у команды и у workspace — обе."""
        labels = [
            label
            for label in await self.labels()
            if team_id is None or label.team_id in (None, team_id)
        ]
        ids: list[UUID] = []
        for name in wanted:
            found = [
                label.id
                for label in labels
                if label.name.casefold() == name.casefold() or str(label.id) == name
            ]
            if not found:
                known = sorted({label.name for label in labels})
                raise ResolveError(
                    "not_found",
                    "label_not_found",
                    f"Метка «{name}» не найдена",
                    f"Доступные: {names(known)}. Метки не создаются сами",
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
        raise ResolveError(
            "not_found",
            "user_not_found",
            f"Участник «{ref}» не найден в workspace",
            "Исполнителем может быть только участник workspace",
        )

    # --- Проекты, задачи, views -------------------------------------------------------

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
        projects = await self.projects()
        matches = [p for p in projects if p.name.casefold() == ref.casefold()]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise ResolveError(
                "ambiguous", "project_ambiguous", f"Проектов «{ref}» несколько", "Укажите id"
            )
        raise ResolveError(
            "not_found",
            "project_not_found",
            f"Проект «{ref}» не найден",
            f"Доступные: {names(sorted(p.name for p in projects))}",
        )

    async def task(self, ref: str, *, expand: tuple[str, ...] = ()) -> Task:
        """Задача по ключу или UUID; ненайденная — с перечнем команд, чтобы проверить ключ."""
        if TASK_KEY.fullmatch(ref):
            ref = ref.upper()
        try:
            return await self.client.tasks.get(ref, expand=expand)
        except NotFoundError as error:
            hint = None
            with contextlib.suppress(TasKanLineError):
                hint = f"Доступные команды: {names([team.key for team in await self.teams()])}"
            raise ResolveError("not_found", error.code, f"Задача {ref} не найдена", hint) from error

    async def view(self, ref: str) -> View:
        """View по id или имени среди видимых."""
        if (value := _uuid(ref)) is not None:
            return await self.client.views.get(value)
        views = await self.client.views.all((await self.workspace()).id)
        matches = [view for view in views if view.name.casefold() == ref.casefold()]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise ResolveError(
                "ambiguous", "view_ambiguous", f"Views с именем «{ref}» несколько", "Укажите id"
            )
        raise ResolveError(
            "not_found",
            "view_not_found",
            f"View «{ref}» не найден",
            f"Доступные: {names([view.name for view in views])}",
        )
