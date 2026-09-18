"""Регистрация, вход и жизненный цикл cookie-сессии."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import RefreshToken
from app.modules.users.models import User

CSRF = {"X-Requested-With": "XMLHttpRequest"}


async def register(
    client: AsyncClient,
    email: str = "ivan@example.com",
    password: str = "correct horse battery",
    full_name: str = "Иван Иванов",
) -> Response:
    return await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
        headers=CSRF,
    )


async def login(
    client: AsyncClient,
    email: str = "ivan@example.com",
    password: str = "correct horse battery",
) -> Response:
    return await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}, headers=CSRF
    )


class TestRegister:
    async def test_creates_user_and_sets_cookies(self, client: AsyncClient) -> None:
        response = await register(client)

        assert response.status_code == 201
        assert response.json()["user"]["email"] == "ivan@example.com"
        assert client.cookies.get("tkl_access")
        assert client.cookies.get("tkl_refresh")

    async def test_does_not_leak_password(self, client: AsyncClient) -> None:
        response = await register(client)

        assert "correct horse battery" not in response.text
        assert "password_hash" not in response.text

    async def test_cookies_are_http_only(self, client: AsyncClient) -> None:
        """Токен в httpOnly-cookie недостижим для скрипта на странице."""
        response = await register(client)

        cookies = response.headers.get_list("set-cookie")
        assert len(cookies) == 2
        assert all("httponly" in cookie.lower() for cookie in cookies)

    async def test_first_user_becomes_superadmin(self, client: AsyncClient) -> None:
        response = await register(client)

        assert response.json()["user"]["role"] == "superadmin"

    async def test_second_user_is_ordinary(self, client: AsyncClient) -> None:
        await register(client, "first@example.com")

        response = await register(client, "second@example.com")

        assert response.json()["user"]["role"] == "user"

    async def test_duplicate_email_is_rejected_case_insensitively(
        self, client: AsyncClient
    ) -> None:
        await register(client, "ivan@example.com")

        response = await register(client, "IVAN@example.com")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "email_already_registered"

    async def test_email_is_stored_lowercased(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await register(client, "Ivan@Example.COM")

        stored = await db_session.scalar(select(User.email))
        assert stored == "ivan@example.com"

    async def test_short_password_is_rejected(self, client: AsyncClient) -> None:
        response = await register(client, password="short")

        assert response.status_code == 422

    async def test_malformed_email_is_rejected(self, client: AsyncClient) -> None:
        response = await register(client, email="не почта")

        assert response.status_code == 422

    async def test_rate_limit_returns_429_with_retry_after(self, client: AsyncClient) -> None:
        for index in range(5):
            await register(client, f"user{index}@example.com")

        response = await register(client, "over@example.com")

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "rate_limited"
        assert int(response.headers["Retry-After"]) > 0


class TestLogin:
    async def test_correct_password_sets_cookies(self, client: AsyncClient) -> None:
        await register(client)
        client.cookies.clear()

        response = await login(client)

        assert response.status_code == 200
        assert response.json()["user"]["email"] == "ivan@example.com"
        assert client.cookies.get("tkl_access")
        assert client.cookies.get("tkl_refresh")

    async def test_wrong_password_is_invalid_credentials(self, client: AsyncClient) -> None:
        await register(client)

        response = await login(client, password="wrong password")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    async def test_unknown_email_gives_the_same_error(self, client: AsyncClient) -> None:
        """Ответ не должен отличать «нет такого email» от «неверный пароль»."""
        await register(client)

        response = await login(client, email="nobody@example.com")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    async def test_inactive_user_gets_the_same_error(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await register(client)
        user = await db_session.scalar(select(User))
        assert user is not None
        user.is_active = False
        await db_session.flush()

        response = await login(client)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    async def test_updates_last_seen_at(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await register(client)
        user = await db_session.scalar(select(User))
        assert user is not None and user.last_seen_at is None

        await login(client)

        await db_session.refresh(user)
        assert user.last_seen_at is not None
        assert datetime.now(UTC) - user.last_seen_at < timedelta(minutes=1)

    async def test_rate_limit_returns_429(self, client: AsyncClient) -> None:
        await register(client)
        for _ in range(10):
            await login(client, password="wrong password")

        response = await login(client, password="wrong password")

        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0


class TestRefresh:
    async def test_rotates_both_cookies(self, session_client: AsyncClient) -> None:
        old_access = session_client.cookies["tkl_access"]
        old_refresh = session_client.cookies["tkl_refresh"]

        response = await session_client.post("/api/v1/auth/refresh", headers=CSRF)

        assert response.status_code == 200
        assert session_client.cookies["tkl_refresh"] != old_refresh
        assert session_client.cookies["tkl_access"] != old_access

    async def test_new_session_keeps_working(self, session_client: AsyncClient) -> None:
        await session_client.post("/api/v1/auth/refresh", headers=CSRF)

        response = await session_client.get("/api/v1/me")

        assert response.status_code == 200

    async def test_old_token_is_reported_as_reuse(
        self, session_client: AsyncClient, client: AsyncClient
    ) -> None:
        old = session_client.cookies["tkl_refresh"]
        await session_client.post("/api/v1/auth/refresh", headers=CSRF)

        client.cookies.set("tkl_refresh", old)
        response = await client.post("/api/v1/auth/refresh", headers=CSRF)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "token_reuse_detected"

    async def test_reuse_revokes_every_session(
        self, session_client: AsyncClient, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Повторное использование отозванного токена гасит все сессии, а не одну."""
        old = session_client.cookies["tkl_refresh"]
        await session_client.post("/api/v1/auth/refresh", headers=CSRF)
        client.cookies.set("tkl_refresh", old)

        await client.post("/api/v1/auth/refresh", headers=CSRF)

        alive = await db_session.scalar(
            select(func.count()).select_from(RefreshToken).where(RefreshToken.revoked_at.is_(None))
        )
        assert alive == 0
        again = await session_client.post("/api/v1/auth/refresh", headers=CSRF)
        assert again.status_code == 401

    async def test_without_cookie_is_401(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/auth/refresh", headers=CSRF)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_token"

    async def test_unknown_token_is_401(self, client: AsyncClient) -> None:
        client.cookies.set("tkl_refresh", "a" * 43)

        response = await client.post("/api/v1/auth/refresh", headers=CSRF)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_token"

    async def test_expired_token_is_401(
        self, session_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token = await db_session.scalar(select(RefreshToken))
        assert token is not None
        token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.flush()

        response = await session_client.post("/api/v1/auth/refresh", headers=CSRF)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_token"


class TestLogout:
    async def test_revokes_token_and_clears_cookies(self, session_client: AsyncClient) -> None:
        response = await session_client.post("/api/v1/auth/logout", headers=CSRF)

        assert response.status_code == 204
        assert not session_client.cookies.get("tkl_access")
        assert not session_client.cookies.get("tkl_refresh")

    async def test_revoked_token_cannot_refresh(
        self, session_client: AsyncClient, client: AsyncClient
    ) -> None:
        refresh = session_client.cookies["tkl_refresh"]
        await session_client.post("/api/v1/auth/logout", headers=CSRF)

        client.cookies.set("tkl_refresh", refresh)
        response = await client.post("/api/v1/auth/refresh", headers=CSRF)

        assert response.status_code == 401

    async def test_is_idempotent(self, client: AsyncClient) -> None:
        """Выход без сессии — не ошибка: результат тот же, что и просили."""
        response = await client.post("/api/v1/auth/logout", headers=CSRF)

        assert response.status_code == 204
