"""Матрица прав §6.3: у каждого защищённого эндпоинта три проверки.

1. Чужак (нет членства в workspace) — 404: существование объекта не подтверждается.
2. Роль на ступень ниже минимальной — 403 insufficient_role. Если ниже минимальной на
   этом уровне ничего нет — гость workspace получает 404 (объект ему не виден).
3. Минимальная роль — успех.

Роль собирается ровно такой, какая нужна: на уровне команды и проекта актор —
гость workspace плюс явное членство, так проверяется именно этот уровень.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import AccessTarget, EffectiveRole
from app.openapi import dump
from tests.org import API, create_project, create_team, create_workspace, grant, user_id_of

SignUp = Callable[..., Awaitable[AsyncClient]]

GUEST, VIEWER, MEMBER, ADMIN, OWNER = (
    EffectiveRole.GUEST,
    EffectiveRole.VIEWER,
    EffectiveRole.MEMBER,
    EffectiveRole.ADMIN,
    EffectiveRole.OWNER,
)

# Какие эффективные роли достижимы на каждом уровне — снизу вверх.
LEVEL_ROLES: dict[AccessTarget, list[EffectiveRole]] = {
    "workspace": [GUEST, MEMBER, ADMIN, OWNER],
    "team": [MEMBER, ADMIN, OWNER],
    "project": [VIEWER, MEMBER, ADMIN, OWNER],
}


@dataclass(frozen=True)
class Case:
    method: str
    path: str
    on: AccessTarget
    minimum: EffectiveRole
    json: dict[str, Any] | None = None

    def __str__(self) -> str:
        suffix = f" {sorted(self.json)}" if self.json else ""
        return f"{self.method} {self.path}{suffix}"


def invitation(scope: str, scope_id: str) -> dict[str, Any]:
    return {"email": "new@example.com", "scope_type": scope, "scope_id": scope_id, "role": "member"}


CASES = [
    Case("GET", "/workspaces/{workspace_id}", "workspace", GUEST),
    Case("PATCH", "/workspaces/{workspace_id}", "workspace", ADMIN, {"name": "Новое имя"}),
    Case("DELETE", "/workspaces/{workspace_id}", "workspace", OWNER),
    Case(
        "POST",
        "/workspaces/{workspace_id}/transfer-ownership",
        "workspace",
        OWNER,
        {"user_id": "{spare_id}"},
    ),
    Case("GET", "/workspaces/{workspace_id}/members", "workspace", MEMBER),
    Case(
        "PATCH",
        "/workspaces/{workspace_id}/members/{user_id}",
        "workspace",
        ADMIN,
        {"role": "admin"},
    ),
    Case("DELETE", "/workspaces/{workspace_id}/members/{user_id}", "workspace", ADMIN),
    Case("GET", "/workspaces/{workspace_id}/teams", "workspace", GUEST),
    Case(
        "POST",
        "/workspaces/{workspace_id}/teams",
        "workspace",
        ADMIN,
        {"key": "OPS", "name": "Эксплуатация"},
    ),
    Case("GET", "/invitations?workspace_id={workspace_id}", "workspace", ADMIN),
    Case("POST", "/invitations", "workspace", ADMIN, invitation("workspace", "{workspace_id}")),
    Case("GET", "/teams/{team_id}", "team", MEMBER),
    Case("PATCH", "/teams/{team_id}", "team", ADMIN, {"name": "Новое имя"}),
    Case("PATCH", "/teams/{team_id}", "team", OWNER, {"key": "NEW"}),
    Case("DELETE", "/teams/{team_id}", "team", OWNER),
    Case("GET", "/teams/{team_id}/members", "team", MEMBER),
    Case("PATCH", "/teams/{team_id}/members/{user_id}", "team", ADMIN, {"role": "lead"}),
    Case("DELETE", "/teams/{team_id}/members/{user_id}", "team", ADMIN),
    Case("GET", "/teams/{team_id}/projects", "team", MEMBER),
    Case("POST", "/teams/{team_id}/projects", "team", MEMBER, {"name": "Новый проект"}),
    Case("POST", "/invitations", "team", ADMIN, invitation("team", "{team_id}")),
    Case("GET", "/projects/{project_id}", "project", VIEWER),
    Case("PATCH", "/projects/{project_id}", "project", MEMBER, {"name": "Новое имя"}),
    Case("POST", "/projects/{project_id}/archive", "project", ADMIN),
    Case("POST", "/projects/{project_id}/unarchive", "project", ADMIN),
    Case("DELETE", "/projects/{project_id}", "project", ADMIN),
    Case("GET", "/projects/{project_id}/members", "project", VIEWER),
    Case("PATCH", "/projects/{project_id}/members/{user_id}", "project", ADMIN, {"role": "admin"}),
    Case("DELETE", "/projects/{project_id}/members/{user_id}", "project", ADMIN),
    Case("POST", "/invitations", "project", ADMIN, invitation("project", "{project_id}")),
]


def fill(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format(**ids)
    if isinstance(value, dict):
        return {key: fill(item, ids) for key, item in value.items()}
    return value


class World:
    """Владелец, пространство, команда, проект и «запасной» участник всех трёх уровней —
    над ним выполняются действия с участниками."""

    def __init__(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        self._sign_up = sign_up
        self._session = db_session
        self.ids: dict[str, str] = {}
        self._count = 0

    async def build(self) -> None:
        owner = await self._sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        project = await create_project(owner, team["id"])
        await self._sign_up("spare@example.com")
        spare = await user_id_of(self._session, "spare@example.com")
        await grant(
            self._session,
            user_id=spare,
            workspace_id=workspace["id"],
            workspace_role="member",
            team_id=team["id"],
            team_role="member",
            project_id=project["id"],
            project_role="member",
        )
        self.ids = {
            "workspace_id": workspace["id"],
            "team_id": team["id"],
            "project_id": project["id"],
            "spare_id": str(spare),
            # Alias: путь реальных маршрутов участников называет параметр `user_id`,
            # а не `spare_id` — приведение к именам маршрутов нужно тесту покрытия ниже.
            "user_id": str(spare),
        }

    async def actor(self, on: AccessTarget | None, role: EffectiveRole | None) -> AsyncClient:
        """Новый пользователь ровно с этой ролью; `on=None` — чужак без членства."""
        self._count += 1
        email = f"actor{self._count}@example.com"
        client = await self._sign_up(email)
        if on is None or role is None:
            return client

        user_id = await user_id_of(self._session, email)
        workspace_role, extra = self._shape(on, role)
        await grant(
            self._session,
            user_id=user_id,
            workspace_id=self.ids["workspace_id"],
            workspace_role=workspace_role,
            **extra,
        )
        return client

    def _shape(self, on: AccessTarget, role: EffectiveRole) -> tuple[str, dict[str, Any]]:
        if role == OWNER:
            return "owner", {}
        if on == "workspace":
            return {GUEST: "guest", MEMBER: "member", ADMIN: "admin"}[role], {}
        if on == "team":
            team_role = {MEMBER: "member", ADMIN: "lead"}[role]
            return "guest", {"team_id": self.ids["team_id"], "team_role": team_role}
        project_role = {VIEWER: "viewer", MEMBER: "member", ADMIN: "admin"}[role]
        return "guest", {"project_id": self.ids["project_id"], "project_role": project_role}


@pytest.mark.parametrize("case", CASES, ids=str)
async def test_permission_matrix(case: Case, sign_up: SignUp, db_session: AsyncSession) -> None:
    world = World(sign_up, db_session)
    await world.build()
    path = API + case.path.format(**world.ids)
    body = fill(case.json, world.ids)

    async def call(client: AsyncClient) -> Any:
        return await client.request(case.method, path, json=body)

    stranger = await call(await world.actor(None, None))
    assert stranger.status_code == 404, stranger.text

    ladder = LEVEL_ROLES[case.on]
    below = ladder[ladder.index(case.minimum) - 1] if ladder.index(case.minimum) > 0 else None
    if below is not None:
        denied = await call(await world.actor(case.on, below))
        assert denied.status_code == 403, denied.text
        assert denied.json()["error"]["code"] == "insufficient_role"
    elif case.on != "workspace":
        # Гость workspace без членства на этом уровне объекта не видит.
        hidden = await call(await world.actor("workspace", GUEST))
        assert hidden.status_code == 404, hidden.text

    allowed = await call(await world.actor(case.on, case.minimum))
    assert allowed.status_code < 400, allowed.text


def test_matrix_covers_every_org_route() -> None:
    """Новый маршрут без строки в матрице — непроверенные права.

    Маршруты берутся из OpenAPI-схемы, а не из `create_app().routes`: на текущей
    FastAPI в `app.routes` лежат обёртки `_IncludedRouter` с `path=None`, и обход
    объектов маршрутов вернул бы пустое множество — проверка стала бы вечно
    зелёной вне зависимости от того, что в неё передали.
    """
    covered = {(case.method, case.path.split("?")[0]) for case in CASES}
    public = {("GET", "/invitations/token/{token}"), ("POST", "/invitations/token/{token}/accept")}
    # Проверяются отдельно: список своих и создание не привязаны к объекту,
    # отзыв приглашения — в test_invitations.
    special = {
        ("GET", "/workspaces"),
        ("POST", "/workspaces"),
        ("DELETE", "/invitations/{invitation_id}"),
    }
    prefixes = ("/workspaces", "/teams", "/projects", "/invitations")
    http_methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}

    paths = json.loads(dump())["paths"]
    routes = {
        (method.upper(), path.removeprefix(API))
        for path, operations in paths.items()
        if path.removeprefix(API).startswith(prefixes)
        for method in operations
        if method in http_methods
    }

    # Страховка от повторного «вечно зелёного» теста: множество не пустое и
    # содержит заведомо существующий маршрут.
    assert routes
    assert ("GET", "/workspaces/{workspace_id}") in routes

    assert routes - covered - public - special == set()
