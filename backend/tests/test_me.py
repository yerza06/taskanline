"""Профиль текущего пользователя."""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.org import create_project, create_team, create_workspace, grant, user_id_of

CSRF = {"X-Requested-With": "XMLHttpRequest"}


class TestReadProfile:
    async def test_returns_profile_and_instance_role(self, session_client: AsyncClient) -> None:
        response = await session_client.get("/api/v1/me")

        body = response.json()
        assert body["email"] == "ivan@example.com"
        assert body["full_name"] == "Иван Иванов"
        assert body["role"] == "superadmin"

    async def test_never_exposes_password_hash(self, session_client: AsyncClient) -> None:
        response = await session_client.get("/api/v1/me")

        assert "password_hash" not in response.text
        assert "argon2" not in response.text


class TestUpdateProfile:
    async def test_updates_full_name(self, session_client: AsyncClient) -> None:
        response = await session_client.patch(
            "/api/v1/me", json={"full_name": "Иван Петров"}, headers=CSRF
        )

        assert response.status_code == 200
        assert response.json()["full_name"] == "Иван Петров"

    async def test_change_is_persisted(self, session_client: AsyncClient) -> None:
        await session_client.patch("/api/v1/me", json={"full_name": "Иван Петров"}, headers=CSRF)

        response = await session_client.get("/api/v1/me")

        assert response.json()["full_name"] == "Иван Петров"

    async def test_rejects_role_escalation(self, session_client: AsyncClient) -> None:
        """Повышение себя до superadmin через профиль должно быть видимой ошибкой."""
        response = await session_client.patch(
            "/api/v1/me", json={"role": "superadmin"}, headers=CSRF
        )

        assert response.status_code == 422

    async def test_rejects_email_change(self, session_client: AsyncClient) -> None:
        response = await session_client.patch(
            "/api/v1/me", json={"email": "other@example.com"}, headers=CSRF
        )

        assert response.status_code == 422

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.patch("/api/v1/me", json={"full_name": "Кто-то"}, headers=CSRF)

        assert response.status_code == 401


async def test_me_lists_memberships(
    sign_up: Callable[..., Awaitable[AsyncClient]], db_session: AsyncSession
) -> None:
    """По членствам подрядчик находит свой проект: команду ему не видно."""
    owner = await sign_up("owner@example.com")
    workspace = await create_workspace(owner)
    team = await create_team(owner, workspace["id"])
    project = await create_project(owner, team["id"])
    anna = await sign_up("anna@example.com")
    await grant(
        db_session,
        user_id=await user_id_of(db_session, "anna@example.com"),
        workspace_id=workspace["id"],
        workspace_role="guest",
        project_id=project["id"],
        project_role="member",
    )

    memberships = (await anna.get("/api/v1/me")).json()["memberships"]

    assert memberships == {
        "workspaces": [{"workspace_id": workspace["id"], "role": "guest"}],
        "teams": [],
        "projects": [
            {"project_id": project["id"], "workspace_id": workspace["id"], "role": "member"}
        ],
    }
