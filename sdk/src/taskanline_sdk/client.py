"""Клиент API TasKanLine: ресурсы по доменам поверх одного `Transport`.

Ссылка на задачу (`ref`) — UUID или ключ `ENG-142` в любом регистре: сервер разбирает
оба. Неоднозначный ключ (одинаковый в двух workspace) уточняется `workspace_id`.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from types import TracebackType
from typing import Any, Self
from uuid import UUID

import httpx
from pydantic import TypeAdapter

from taskanline_sdk.models import (
    Activity,
    Comment,
    Invitation,
    Label,
    Me,
    Member,
    Notification,
    Page,
    Project,
    Relation,
    State,
    Task,
    Team,
    View,
    ViewResult,
    Workspace,
)
from taskanline_sdk.transport import Sleep, Transport

Id = UUID | str


def _items[T](model: type[T], body: Any) -> list[T]:
    return TypeAdapter(list[model]).validate_python(body["items"])  # type: ignore[valid-type]


def _expand(fields: Iterable[str]) -> str | None:
    joined = ",".join(fields)
    return joined or None


async def paginate[T](fetch: Callable[[str | None], Awaitable[Page[T]]]) -> AsyncIterator[T]:
    """Все элементы курсорного списка подряд: следующая страница — по мере чтения."""
    cursor: str | None = None
    while True:
        page = await fetch(cursor)
        for item in page.items:
            yield item
        if not page.has_more or page.next_cursor is None:
            return
        cursor = page.next_cursor


class _Resource:
    def __init__(self, transport: Transport) -> None:
        self._t = transport


class MeResource(_Resource):
    async def get(self) -> Me:
        return Me.model_validate(await self._t.request("GET", "/me"))

    async def notifications(
        self, *, unread: bool = False, limit: int | None = None, cursor: str | None = None
    ) -> Page[Notification]:
        body = await self._t.request(
            "GET",
            "/me/notifications",
            params={"unread": unread or None, "limit": limit, "cursor": cursor},
        )
        return Page[Notification].model_validate(body)

    async def mark_read(self, notification_id: Id) -> None:
        await self._t.request("POST", f"/me/notifications/{notification_id}/read")


class WorkspacesResource(_Resource):
    async def all(self) -> list[Workspace]:
        return _items(Workspace, await self._t.request("GET", "/workspaces"))

    async def get(self, workspace_id: Id) -> Workspace:
        return Workspace.model_validate(await self._t.request("GET", f"/workspaces/{workspace_id}"))

    async def create(self, *, name: str, slug: str) -> Workspace:
        body = await self._t.request("POST", "/workspaces", json={"name": name, "slug": slug})
        return Workspace.model_validate(body)

    async def members(self, workspace_id: Id) -> list[Member]:
        return _items(Member, await self._t.request("GET", f"/workspaces/{workspace_id}/members"))


class TeamsResource(_Resource):
    async def all(self, workspace_id: Id) -> list[Team]:
        return _items(Team, await self._t.request("GET", f"/workspaces/{workspace_id}/teams"))

    async def get(self, team_id: Id) -> Team:
        return Team.model_validate(await self._t.request("GET", f"/teams/{team_id}"))

    async def create(
        self,
        workspace_id: Id,
        *,
        key: str,
        name: str,
        description: str | None = None,
        is_private: bool = False,
    ) -> Team:
        body = await self._t.request(
            "POST",
            f"/workspaces/{workspace_id}/teams",
            json={"key": key, "name": name, "description": description, "is_private": is_private},
        )
        return Team.model_validate(body)

    async def members(self, team_id: Id) -> list[Member]:
        return _items(Member, await self._t.request("GET", f"/teams/{team_id}/members"))

    async def states(self, team_id: Id) -> list[State]:
        return _items(State, await self._t.request("GET", f"/teams/{team_id}/states"))


class ProjectsResource(_Resource):
    async def all(self, team_id: Id, *, include_archived: bool = False) -> list[Project]:
        body = await self._t.request(
            "GET",
            f"/teams/{team_id}/projects",
            params={"include_archived": include_archived or None},
        )
        return _items(Project, body)

    async def get(self, project_id: Id) -> Project:
        return Project.model_validate(await self._t.request("GET", f"/projects/{project_id}"))

    async def create(self, team_id: Id, *, name: str, **fields: Any) -> Project:
        """Необязательные поля: description, status, lead_id, start_date, target_date."""
        body = await self._t.request(
            "POST", f"/teams/{team_id}/projects", json={"name": name, **fields}
        )
        return Project.model_validate(body)

    async def update(self, project_id: Id, **changes: Any) -> Project:
        """Переданное поле меняется; `None` очищает необязательное."""
        body = await self._t.request("PATCH", f"/projects/{project_id}", json=changes)
        return Project.model_validate(body)

    async def archive(self, project_id: Id) -> Project:
        body = await self._t.request("POST", f"/projects/{project_id}/archive")
        return Project.model_validate(body)

    async def members(self, project_id: Id) -> list[Member]:
        return _items(Member, await self._t.request("GET", f"/projects/{project_id}/members"))


class InvitationsResource(_Resource):
    async def create(self, *, email: str, scope_type: str, scope_id: Id, role: str) -> Invitation:
        body = await self._t.request(
            "POST",
            "/invitations",
            json={"email": email, "scope_type": scope_type, "scope_id": scope_id, "role": role},
        )
        return Invitation.model_validate(body)


class LabelsResource(_Resource):
    async def all(self, workspace_id: Id, *, team_id: Id | None = None) -> list[Label]:
        body = await self._t.request(
            "GET", "/labels", params={"workspace_id": workspace_id, "team_id": team_id}
        )
        return _items(Label, body)

    async def create(
        self, workspace_id: Id, *, name: str, color: str, team_id: Id | None = None
    ) -> Label:
        body = await self._t.request(
            "POST",
            "/labels",
            json={"workspace_id": workspace_id, "team_id": team_id, "name": name, "color": color},
        )
        return Label.model_validate(body)

    async def delete(self, label_id: Id) -> None:
        await self._t.request("DELETE", f"/labels/{label_id}")


class TasksResource(_Resource):
    async def page(
        self,
        workspace_id: Id,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        expand: Iterable[str] = (),
        **filters: Any,
    ) -> Page[Task]:
        """`GET /tasks`: фильтры — его query-параметры (`team_id`, `assignee_id=["me"]`, …)."""
        params = {"workspace_id": workspace_id, "limit": limit, "cursor": cursor, **filters}
        body = await self._t.request("GET", "/tasks", params={**params, "expand": _expand(expand)})
        return Page[Task].model_validate(body)

    async def query(
        self,
        workspace_id: Id,
        *,
        filters: dict[str, Any] | None = None,
        sort_by: str = "manual",
        sort_direction: str = "asc",
        group_by: str | None = None,
        group: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        expand: Iterable[str] = (),
    ) -> ViewResult:
        """Несохранённый view — фильтры в грамматике views (§4 модели данных)."""
        payload: dict[str, Any] = {
            "workspace_id": workspace_id,
            "filters": filters or {},
            "sort_by": sort_by,
            "sort_direction": sort_direction,
            "group_by": group_by,
            "group": group,
            "cursor": cursor,
        }
        if limit is not None:
            payload["limit"] = limit
        body = await self._t.request(
            "POST", "/views/query", json=payload, params={"expand": _expand(expand)}
        )
        return ViewResult.model_validate(body)

    async def iter_query(self, workspace_id: Id, **options: Any) -> AsyncIterator[Task]:
        """Все задачи несохранённого view без группировки — страницу за страницей."""

        async def fetch(cursor: str | None) -> Page[Task]:
            (group,) = (await self.query(workspace_id, cursor=cursor, **options)).groups
            return Page[Task](
                items=group.items, next_cursor=group.next_cursor, has_more=group.has_more
            )

        async for task in paginate(fetch):
            yield task

    async def get(
        self, ref: Id, *, workspace_id: Id | None = None, expand: Iterable[str] = ()
    ) -> Task:
        body = await self._t.request(
            "GET",
            f"/tasks/{ref}",
            params={"workspace_id": workspace_id, "expand": _expand(expand)},
        )
        return Task.model_validate(body)

    async def create(
        self,
        *,
        title: str,
        team_id: Id | None = None,
        project_id: Id | None = None,
        expand: Iterable[str] = (),
        idempotency_key: str | None = None,
        **fields: Any,
    ) -> Task:
        """Создание идемпотентно: ключ, не переданный явно, SDK придумывает сам —
        и повтор после сетевого сбоя возвращает ту же задачу, а не создаёт вторую.

        Необязательные поля: description, state_id, assignee_id, priority, due_date,
        parent_id, label_ids.
        """
        payload = {"title": title, "team_id": team_id, "project_id": project_id, **fields}
        body = await self._t.request(
            "POST",
            "/tasks",
            json={key: value for key, value in payload.items() if value is not None},
            params={"expand": _expand(expand)},
            headers={"Idempotency-Key": idempotency_key or str(uuid.uuid4())},
        )
        return Task.model_validate(body)

    async def update(
        self,
        ref: Id,
        *,
        workspace_id: Id | None = None,
        expand: Iterable[str] = (),
        **changes: Any,
    ) -> Task:
        """Переданное поле меняется; `None` очищает необязательное."""
        body = await self._t.request(
            "PATCH",
            f"/tasks/{ref}",
            json=changes,
            params={"workspace_id": workspace_id, "expand": _expand(expand)},
        )
        return Task.model_validate(body)

    async def delete(self, ref: Id, *, workspace_id: Id | None = None) -> None:
        await self._t.request("DELETE", f"/tasks/{ref}", params={"workspace_id": workspace_id})

    async def restore(self, ref: Id, *, workspace_id: Id | None = None) -> Task:
        body = await self._t.request(
            "POST", f"/tasks/{ref}/restore", params={"workspace_id": workspace_id}
        )
        return Task.model_validate(body)

    async def move(
        self,
        ref: Id,
        *,
        after: Id | None = None,
        before: Id | None = None,
        position: str | None = None,
        state_id: Id | None = None,
        workspace_id: Id | None = None,
    ) -> Task:
        """Сосед (`after`/`before`) или край (`position` = top | bottom), и/или статус."""
        payload = {
            "after_id": after,
            "before_id": before,
            "position": position,
            "state_id": state_id,
        }
        body = await self._t.request(
            "POST",
            f"/tasks/{ref}/move",
            json={key: value for key, value in payload.items() if value is not None},
            params={"workspace_id": workspace_id},
        )
        return Task.model_validate(body)

    async def subtasks(
        self, ref: Id, *, workspace_id: Id | None = None, expand: Iterable[str] = ()
    ) -> list[Task]:
        body = await self._t.request(
            "GET",
            f"/tasks/{ref}/subtasks",
            params={"workspace_id": workspace_id, "expand": _expand(expand)},
        )
        return _items(Task, body)

    async def add_relation(
        self, ref: Id, *, kind: str, target: Id, workspace_id: Id | None = None
    ) -> Relation:
        """`kind` — со стороны этой задачи: blocks, blocked_by, relates_to, duplicates, …"""
        body = await self._t.request(
            "POST",
            f"/tasks/{ref}/relations",
            json={"type": kind, "target_id": target},
            params={"workspace_id": workspace_id},
        )
        return Relation.model_validate(body)

    async def remove_relation(
        self, ref: Id, relation_id: Id, *, workspace_id: Id | None = None
    ) -> None:
        await self._t.request(
            "DELETE", f"/tasks/{ref}/relations/{relation_id}", params={"workspace_id": workspace_id}
        )

    async def set_labels(
        self, ref: Id, label_ids: Iterable[Id], *, workspace_id: Id | None = None
    ) -> Task:
        body = await self._t.request(
            "PUT",
            f"/tasks/{ref}/labels",
            json={"label_ids": list(label_ids)},
            params={"workspace_id": workspace_id},
        )
        return Task.model_validate(body)

    async def activities(
        self, ref: Id, *, limit: int | None = None, cursor: str | None = None
    ) -> Page[Activity]:
        body = await self._t.request(
            "GET", f"/tasks/{ref}/activities", params={"limit": limit, "cursor": cursor}
        )
        return Page[Activity].model_validate(body)

    async def comments(
        self, ref: Id, *, limit: int | None = None, cursor: str | None = None
    ) -> Page[Comment]:
        body = await self._t.request(
            "GET", f"/tasks/{ref}/comments", params={"limit": limit, "cursor": cursor}
        )
        return Page[Comment].model_validate(body)

    async def comment(self, ref: Id, body: str, *, parent_id: Id | None = None) -> Comment:
        payload: dict[str, Any] = {"body": body}
        if parent_id is not None:
            payload["parent_id"] = parent_id
        return Comment.model_validate(
            await self._t.request("POST", f"/tasks/{ref}/comments", json=payload)
        )


class ViewsResource(_Resource):
    async def all(self, workspace_id: Id) -> list[View]:
        body = await self._t.request("GET", "/views", params={"workspace_id": workspace_id})
        return _items(View, body)

    async def get(self, view_id: Id) -> View:
        return View.model_validate(await self._t.request("GET", f"/views/{view_id}"))

    async def create(
        self, workspace_id: Id, *, name: str, scope: str = "user", **fields: Any
    ) -> View:
        """Необязательные поля: team_id, filters, group_by, sort_by, sort_direction, layout, …"""
        payload = {"workspace_id": workspace_id, "name": name, "scope": scope, **fields}
        body = await self._t.request(
            "POST",
            "/views",
            json={key: value for key, value in payload.items() if value is not None},
        )
        return View.model_validate(body)

    async def update(self, view_id: Id, **changes: Any) -> View:
        return View.model_validate(
            await self._t.request("PATCH", f"/views/{view_id}", json=changes)
        )

    async def delete(self, view_id: Id) -> None:
        await self._t.request("DELETE", f"/views/{view_id}")

    async def run(
        self,
        view_id: Id,
        *,
        group: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        expand: Iterable[str] = (),
    ) -> ViewResult:
        body = await self._t.request(
            "GET",
            f"/views/{view_id}/tasks",
            params={"group": group, "limit": limit, "cursor": cursor, "expand": _expand(expand)},
        )
        return ViewResult.model_validate(body)


class TasKanLineClient:
    """Асинхронный клиент; закрывается через `async with` или `aclose()`.

    `transport` и `sleep` подменяются в тестах: первый — чтобы ходить в приложение
    без сети, второй — чтобы паузы между ретраями не тормозили тесты.
    """

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep | None = None,
    ) -> None:
        extra: dict[str, Any] = {"sleep": sleep} if sleep is not None else {}
        self._transport = Transport(
            base_url,
            token,
            timeout=timeout,
            max_retries=max_retries,
            backoff=backoff,
            transport=transport,
            **extra,
        )
        self.me = MeResource(self._transport)
        self.workspaces = WorkspacesResource(self._transport)
        self.teams = TeamsResource(self._transport)
        self.projects = ProjectsResource(self._transport)
        self.invitations = InvitationsResource(self._transport)
        self.labels = LabelsResource(self._transport)
        self.tasks = TasksResource(self._transport)
        self.views = ViewsResource(self._transport)

    @property
    def api_url(self) -> str:
        return self._transport.base_url

    async def request(self, method: str, path: str, **options: Any) -> Any:
        """Запрос мимо ресурсов — для эндпоинтов, до которых SDK ещё не дорос."""
        return await self._transport.request(method, path, **options)

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()
