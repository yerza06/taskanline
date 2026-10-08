"""Транспорт SDK: адрес, авторизация, параметры, ошибки и ретраи."""

import json

import httpx
import pytest

from sdk_tests.fake import TASK, Fake, error
from taskanline_sdk import (
    ApiError,
    AuthenticationError,
    ConflictError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from taskanline_sdk.transport import api_root


@pytest.mark.parametrize(
    "base", ["https://tkl.example", "https://tkl.example/", "https://tkl.example/api/v1/"]
)
def test_api_root_is_added_once(base: str) -> None:
    assert api_root(base) == "https://tkl.example/api/v1"


async def test_token_and_params() -> None:
    fake = Fake(httpx.Response(200, json={"items": [], "next_cursor": None, "has_more": False}))

    async with fake.client() as client:
        await client.tasks.page(
            "ws", assignee_id=["me", "none"], q=None, deleted=False, expand=["state", "labels"]
        )

    (request,) = fake.requests
    assert request.headers["Authorization"] == "Bearer tkl_secret"
    assert request.url.path == "/api/v1/tasks"
    assert request.url.params.get_list("assignee_id") == ["me", "none"]
    assert request.url.params["deleted"] == "false"
    assert request.url.params["expand"] == "state,labels"
    assert "q" not in request.url.params


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (400, ValidationError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (409, ConflictError),
        (422, ValidationError),
        (418, ApiError),
    ],
)
async def test_status_maps_to_exception(status: int, kind: type[ApiError]) -> None:
    fake = Fake(error(status, "some_code", "Текст"))

    async with fake.client() as client:
        with pytest.raises(kind) as caught:
            await client.tasks.get("ENG-1")

    assert type(caught.value) is kind
    assert (caught.value.status, caught.value.code, caught.value.message) == (
        status,
        "some_code",
        "Текст",
    )
    assert len(fake.requests) == 1  # 4xx не повторяется


async def test_body_without_envelope() -> None:
    fake = Fake(httpx.Response(502, text="Bad Gateway"))

    async with fake.client(max_retries=0) as client:
        with pytest.raises(ServerError) as caught:
            await client.me.get()

    assert caught.value.code == "http_502"


async def test_rate_limit_waits_retry_after_then_succeeds() -> None:
    me = {
        "id": TASK["creator_id"],
        "email": "a@b.c",
        "full_name": "A",
        "role": "user",
        "created_at": "2026-10-08T10:00:00Z",
        "auth_method": "token",
        "scopes": ["read"],
        "memberships": {"workspaces": [], "teams": [], "projects": []},
        "added_later": "игнорируется",
    }
    fake = Fake(error(429, "rate_limited", **{"Retry-After": "7"}), httpx.Response(200, json=me))

    async with fake.client() as client:
        result = await client.me.get()

    assert result.email == "a@b.c"
    assert fake.sleeps == [7.0]


async def test_rate_limit_gives_up_with_retry_after() -> None:
    fake = Fake(error(429, "rate_limited", **{"Retry-After": "3"}))

    async with fake.client(max_retries=2) as client:
        with pytest.raises(RateLimitError) as caught:
            await client.me.get()

    assert caught.value.retry_after == 3.0
    assert len(fake.requests) == 3


async def test_too_long_retry_after_is_not_waited() -> None:
    fake = Fake(error(429, "rate_limited", **{"Retry-After": "3600"}))

    async with fake.client() as client:
        with pytest.raises(RateLimitError):
            await client.me.get()

    assert fake.sleeps == []


async def test_server_error_retried_with_exponential_backoff_on_get() -> None:
    fake = Fake(error(503, "unavailable"))

    async with fake.client(max_retries=3, backoff=0.5) as client:
        with pytest.raises(ServerError):
            await client.tasks.get("ENG-1")

    assert fake.sleeps == [0.5, 1.0, 2.0]
    assert len(fake.requests) == 4


async def test_server_error_not_retried_on_plain_post() -> None:
    fake = Fake(error(500, "internal"))

    async with fake.client() as client:
        with pytest.raises(ServerError):
            await client.tasks.comment("ENG-1", "текст")

    assert len(fake.requests) == 1


async def test_task_creation_is_retried_with_the_same_idempotency_key() -> None:
    fake = Fake(error(500, "internal"), httpx.Response(201, json=TASK))

    async with fake.client() as client:
        task = await client.tasks.create(title="Починить логин", team_id="team")

    first, second = fake.requests
    assert task.key == "ENG-1"
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"]
    assert json.loads(second.content) == {"title": "Починить логин", "team_id": "team"}


async def test_network_failure_becomes_network_error() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    fake = Fake(broken)

    async with fake.client(max_retries=1) as client:
        with pytest.raises(NetworkError):
            await client.tasks.get("ENG-1")

    assert len(fake.requests) == 2


async def test_timeout_on_post_is_not_retried() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    fake = Fake(slow)

    async with fake.client() as client:
        with pytest.raises(NetworkError):
            await client.tasks.comment("ENG-1", "текст")

    assert len(fake.requests) == 1
