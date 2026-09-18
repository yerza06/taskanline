"""Токены агента: выпуск, список, отзыв и ограничение по scope."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.modules.auth.models import ApiToken

CSRF = {"X-Requested-With": "XMLHttpRequest"}

IssueToken = Callable[..., Awaitable[str]]


class TestIssue:
    async def test_full_token_is_returned_once(self, session_client: AsyncClient) -> None:
        created = await session_client.post(
            "/api/v1/me/tokens", json={"name": "claude-code", "scope": "read_write"}, headers=CSRF
        )

        assert created.status_code == 201
        token = created.json()["token"]
        assert token.startswith("tkl_")

        listed = await session_client.get("/api/v1/me/tokens")
        assert listed.json()["items"][0]["prefix"] == token[:12]
        assert "token" not in listed.json()["items"][0]

    async def test_full_token_is_not_stored(
        self, session_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """В базе только хеш: восстановить показанный токен неоткуда."""
        created = await session_client.post(
            "/api/v1/me/tokens", json={"name": "agent", "scope": "read"}, headers=CSRF
        )

        stored = await db_session.scalar(select(ApiToken))
        assert stored is not None
        assert created.json()["token"] not in stored.token_hash

    async def test_unknown_scope_is_rejected(self, session_client: AsyncClient) -> None:
        response = await session_client.post(
            "/api/v1/me/tokens", json={"name": "agent", "scope": "admin"}, headers=CSRF
        )

        assert response.status_code == 422

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/me/tokens", json={"name": "agent", "scope": "read"}, headers=CSRF
        )

        assert response.status_code == 401


class TestAuthentication:
    async def test_token_authenticates_me(
        self, client: AsyncClient, issue_token: IssueToken
    ) -> None:
        token = await issue_token("read_write")

        response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["auth_method"] == "token"
        assert response.json()["email"] == "ivan@example.com"

    async def test_bearer_wins_over_cookie(
        self, session_client: AsyncClient, issue_token: IssueToken
    ) -> None:
        """Токен важнее оставшейся cookie: иначе ограничение scope обходится."""
        token = await issue_token("read")

        response = await session_client.get(
            "/api/v1/me", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.json()["auth_method"] == "token"
        assert response.json()["scopes"] == ["read"]

    async def test_read_scope_is_blocked_on_mutation(
        self, client: AsyncClient, issue_token: IssueToken
    ) -> None:
        token = await issue_token("read")
        headers = {"Authorization": f"Bearer {token}"}

        read = await client.get("/api/v1/me", headers=headers)
        write = await client.patch("/api/v1/me", json={"full_name": "Новое"}, headers=headers)

        assert read.status_code == 200
        assert write.status_code == 403
        assert write.json()["error"]["code"] == "insufficient_scope"

    async def test_read_write_scope_passes_mutation(
        self, client: AsyncClient, issue_token: IssueToken
    ) -> None:
        token = await issue_token("read_write")

        response = await client.patch(
            "/api/v1/me",
            json={"full_name": "Новое имя"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

    async def test_expired_token_is_rejected(
        self, client: AsyncClient, issue_token: IssueToken, db_session: AsyncSession
    ) -> None:
        token = await issue_token("read")
        stored = await db_session.scalar(select(ApiToken))
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.flush()

        response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_token"

    async def test_last_used_at_is_written_once_per_minute(
        self, client: AsyncClient, issue_token: IssueToken, db_session: AsyncSession
    ) -> None:
        """Запись на каждый запрос агента греет базу без нового смысла."""
        token = await issue_token("read")
        headers = {"Authorization": f"Bearer {token}"}

        await client.get("/api/v1/me", headers=headers)
        stored = await db_session.scalar(select(ApiToken))
        assert stored is not None
        await db_session.refresh(stored)
        first = stored.last_used_at
        assert first is not None

        await client.get("/api/v1/me", headers=headers)
        await db_session.refresh(stored)
        assert stored.last_used_at == first

        stored.last_used_at = datetime.now(UTC) - timedelta(minutes=2)
        await db_session.flush()
        await client.get("/api/v1/me", headers=headers)
        await db_session.refresh(stored)
        assert stored.last_used_at is not None
        assert stored.last_used_at > first


class TestRevoke:
    async def test_revoked_token_stops_working(
        self, session_client: AsyncClient, client: AsyncClient, issue_token: IssueToken
    ) -> None:
        token = await issue_token("read")
        token_id = (await session_client.get("/api/v1/me/tokens")).json()["items"][0]["id"]

        deleted = await session_client.delete(f"/api/v1/me/tokens/{token_id}", headers=CSRF)

        assert deleted.status_code == 204
        response = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    async def test_revoked_token_disappears_from_list(
        self, session_client: AsyncClient, issue_token: IssueToken
    ) -> None:
        await issue_token("read")
        token_id = (await session_client.get("/api/v1/me/tokens")).json()["items"][0]["id"]

        await session_client.delete(f"/api/v1/me/tokens/{token_id}", headers=CSRF)

        assert (await session_client.get("/api/v1/me/tokens")).json()["items"] == []

    async def test_unknown_token_is_404(self, session_client: AsyncClient) -> None:
        response = await session_client.delete(f"/api/v1/me/tokens/{uuid7()}", headers=CSRF)

        assert response.status_code == 404

    async def test_someone_elses_token_is_404_not_403(
        self, session_client: AsyncClient, client: AsyncClient, issue_token: IssueToken
    ) -> None:
        """Чужой объект не подтверждает своё существование даже кодом ответа."""
        await issue_token("read")
        token_id = (await session_client.get("/api/v1/me/tokens")).json()["items"][0]["id"]
        session_client.cookies.clear()
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "other@example.com",
                "password": "correct horse battery",
                "full_name": "Пётр",
            },
            headers=CSRF,
        )

        response = await client.delete(f"/api/v1/me/tokens/{token_id}", headers=CSRF)

        assert response.status_code == 404

    async def test_list_shows_only_own_tokens(
        self, session_client: AsyncClient, client: AsyncClient, issue_token: IssueToken
    ) -> None:
        await issue_token("read")
        session_client.cookies.clear()
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "other@example.com",
                "password": "correct horse battery",
                "full_name": "Пётр",
            },
            headers=CSRF,
        )

        response = await client.get("/api/v1/me/tokens")

        assert response.json()["items"] == []
