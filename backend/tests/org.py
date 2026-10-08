"""Помощники тестов организационной структуры."""

import re
from typing import Any
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail import MailMessage
from app.modules.projects.models import ProjectMember
from app.modules.teams.models import TeamMember
from app.modules.users.models import User
from app.modules.workspaces.models import WorkspaceMember

API = "/api/v1"
CSRF = {"X-Requested-With": "XMLHttpRequest"}
PASSWORD = "correct horse battery"


async def create_workspace(
    client: AsyncClient, *, slug: str = "acme", name: str = "Acme"
) -> dict[str, Any]:
    response = await client.post(f"{API}/workspaces", json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def create_team(
    client: AsyncClient,
    workspace_id: str,
    *,
    key: str = "ENG",
    name: str = "Engineering",
    is_private: bool = False,
) -> dict[str, Any]:
    response = await client.post(
        f"{API}/workspaces/{workspace_id}/teams",
        json={"key": key, "name": name, "is_private": is_private},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def create_project(
    client: AsyncClient, team_id: str, *, name: str = "Сайт", **fields: Any
) -> dict[str, Any]:
    response = await client.post(f"{API}/teams/{team_id}/projects", json={"name": name, **fields})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


class RecordingMailer:
    """Почтальон тестов: складывает письма в список вместо отправки."""

    def __init__(self) -> None:
        self.sent: list[MailMessage] = []

    async def send(self, message: MailMessage) -> None:
        self.sent.append(message)


def invite_token(mailer: RecordingMailer) -> str:
    """Токен из последнего письма: API его не возвращает нигде, как и в жизни."""
    match = re.search(r"/invite/([0-9A-Za-z]+)", mailer.sent[-1].body)
    assert match is not None, mailer.sent[-1].body
    return match.group(1)


async def user_id_of(session: AsyncSession, email: str) -> UUID:
    user_id = await session.scalar(select(User.id).where(User.email == email))
    assert user_id is not None, f"нет пользователя {email}"
    return user_id


async def grant(
    session: AsyncSession,
    *,
    user_id: UUID,
    workspace_id: str | UUID,
    workspace_role: str,
    team_id: str | UUID | None = None,
    team_role: str | None = None,
    project_id: str | UUID | None = None,
    project_role: str | None = None,
) -> None:
    """Членства напрямую в базе — минуя приглашения, которые проверяются отдельно."""
    workspace = UUID(str(workspace_id))
    session.add(WorkspaceMember(workspace_id=workspace, user_id=user_id, role=workspace_role))
    await session.flush()
    if team_id is not None and team_role is not None:
        session.add(
            TeamMember(
                workspace_id=workspace, team_id=UUID(str(team_id)), user_id=user_id, role=team_role
            )
        )
    if project_id is not None and project_role is not None:
        session.add(
            ProjectMember(
                workspace_id=workspace,
                project_id=UUID(str(project_id)),
                user_id=user_id,
                role=project_role,
            )
        )
    await session.flush()


async def team_states(client: AsyncClient, team_id: str) -> dict[str, dict[str, Any]]:
    """Статусы команды по названию: `states["In Progress"]["id"]`."""
    response = await client.get(f"{API}/teams/{team_id}/states")
    assert response.status_code == 200, response.text
    return {state["name"]: state for state in response.json()["items"]}


async def create_task(
    client: AsyncClient, *, title: str = "Задача", **fields: Any
) -> dict[str, Any]:
    response = await client.post(f"{API}/tasks", json={"title": title, **fields})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def activity_types(client: AsyncClient, task: str) -> list[str]:
    """Типы событий истории — от старых к новым."""
    response = await client.get(f"{API}/tasks/{task}/activities", params={"limit": 100})
    assert response.status_code == 200, response.text
    return [item["type"] for item in reversed(response.json()["items"])]
