"""Защита от CSRF: заголовок обязателен там, где cookie прикладывает браузер."""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

CSRF = {"X-Requested-With": "XMLHttpRequest"}

IssueToken = Callable[..., Awaitable[str]]


class TestSessionMutations:
    async def test_mutation_without_header_is_rejected(self, session_client: AsyncClient) -> None:
        response = await session_client.patch("/api/v1/me", json={"full_name": "Без заголовка"})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "csrf_required"

    async def test_mutation_with_header_passes(self, session_client: AsyncClient) -> None:
        response = await session_client.patch(
            "/api/v1/me", json={"full_name": "С заголовком"}, headers=CSRF
        )

        assert response.status_code == 200

    async def test_wrong_header_value_is_rejected(self, session_client: AsyncClient) -> None:
        response = await session_client.patch(
            "/api/v1/me",
            json={"full_name": "Чужое значение"},
            headers={"X-Requested-With": "curl"},
        )

        assert response.status_code == 403

    async def test_delete_is_covered_too(self, session_client: AsyncClient) -> None:
        response = await session_client.delete(
            "/api/v1/me/tokens/00000000-0000-0000-0000-000000000000"
        )

        assert response.status_code == 403

    async def test_refresh_is_covered_too(self, session_client: AsyncClient) -> None:
        """Ротацию сессии тоже нельзя вызывать со стороннего сайта."""
        response = await session_client.post("/api/v1/auth/refresh")

        assert response.status_code == 403


class TestNotApplicable:
    async def test_read_needs_no_header(self, session_client: AsyncClient) -> None:
        response = await session_client.get("/api/v1/me")

        assert response.status_code == 200

    async def test_bearer_mutation_needs_no_header(
        self, client: AsyncClient, issue_token: IssueToken
    ) -> None:
        """Агент не браузер: cookie он не носит, и подставить её ему нечем."""
        token = await issue_token("read_write")

        response = await client.patch(
            "/api/v1/me",
            json={"full_name": "Агент"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

    async def test_login_without_cookies_needs_no_header(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "ivan@example.com",
                "password": "correct horse battery",
                "full_name": "Иван",
            },
            headers=CSRF,
        )
        client.cookies.clear()

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "ivan@example.com", "password": "correct horse battery"},
        )

        assert response.status_code == 200
