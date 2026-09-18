"""Резолвинг Principal: cookie-сессия человека и токен агента."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import issue_access_token
from app.modules.users.models import User


class TestSessionPrincipal:
    async def test_cookie_gives_read_and_write(self, session_client: AsyncClient) -> None:
        response = await session_client.get("/api/v1/me")

        assert response.status_code == 200
        assert response.json()["auth_method"] == "session"
        assert sorted(response.json()["scopes"]) == ["read", "write"]

    async def test_no_credentials_is_unauthorized(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/me")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"

    async def test_expired_access_cookie_is_rejected(
        self, client: AsyncClient, session_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await db_session.scalar(select(User))
        assert user is not None
        expired = issue_access_token(user.id, now=datetime.now(UTC) - timedelta(hours=1))
        client.cookies.set("tkl_access", expired)

        response = await client.get("/api/v1/me")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_token"

    async def test_garbage_cookie_is_rejected(self, client: AsyncClient) -> None:
        client.cookies.set("tkl_access", "not-a-token")

        response = await client.get("/api/v1/me")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_token"

    async def test_deactivated_user_loses_access(
        self, session_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Отключение учётной записи действует немедленно, а не по истечении токена."""
        user = await db_session.scalar(select(User))
        assert user is not None
        user.is_active = False
        await db_session.flush()

        response = await session_client.get("/api/v1/me")

        assert response.status_code == 401

    async def test_cookie_of_deleted_user_is_rejected(
        self, session_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await db_session.scalar(select(User))
        assert user is not None
        await db_session.delete(user)
        await db_session.flush()

        response = await session_client.get("/api/v1/me")

        assert response.status_code == 401


class TestBearerPrincipal:
    async def test_garbage_bearer_is_invalid_token(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/me", headers={"Authorization": "Bearer garbage"})

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_token"

    async def test_unknown_scheme_is_invalid_token(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_token"

    async def test_unknown_pat_is_invalid_token(self, client: AsyncClient) -> None:
        response = await client.get(
            "/api/v1/me", headers={"Authorization": "Bearer tkl_" + "0" * 43}
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_token"
