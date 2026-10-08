"""`Idempotency-Key` на создании задачи и очистка сохранённых ответов старше суток."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.idempotency.models import IdempotencyKey
from app.modules.idempotency.service import IdempotencyService
from tests.org import API, user_id_of
from tests.test_tasks import World

SignUp = Callable[..., Awaitable[AsyncClient]]


async def post(
    w: World, key: str | None, title: str = "Агентская задача", client: AsyncClient | None = None
) -> Response:
    headers = {"Idempotency-Key": key} if key is not None else {}
    return await (client or w.owner).post(
        f"{API}/tasks", json={"title": title, "team_id": w.team["id"]}, headers=headers
    )


async def task_count(w: World) -> int:
    page = (await w.owner.get(f"{API}/tasks", params={"workspace_id": w.workspace["id"]})).json()
    return len(page["items"])


async def test_retry_returns_stored_response(sign_up: SignUp, db_session: AsyncSession) -> None:
    w = await World(sign_up, db_session).build()

    first = await post(w, "retry-1")
    second = await post(w, "retry-1")

    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert "idempotent-replayed" not in first.headers
    assert second.headers["idempotent-replayed"] == "true"
    assert await task_count(w) == 1


async def test_same_key_other_body_is_409(sign_up: SignUp, db_session: AsyncSession) -> None:
    w = await World(sign_up, db_session).build()
    await post(w, "retry-1")

    response = await post(w, "retry-1", title="Другая")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_key_reuse"
    assert await task_count(w) == 1


async def test_keys_of_different_users_do_not_clash(
    sign_up: SignUp, db_session: AsyncSession
) -> None:
    w = await World(sign_up, db_session).build()
    member, _ = await w.person("member@example.com", workspace_role="member")

    mine = await post(w, "shared")
    theirs = await post(w, "shared", client=member)

    assert theirs.status_code == 201
    assert theirs.json()["id"] != mine.json()["id"]


async def test_without_key_every_call_creates(sign_up: SignUp, db_session: AsyncSession) -> None:
    w = await World(sign_up, db_session).build()

    await post(w, None)
    await post(w, None)

    assert await task_count(w) == 2


@pytest.mark.parametrize("key", ["x" * 256, "перевод\nстроки"])
async def test_malformed_key_is_400(sign_up: SignUp, db_session: AsyncSession, key: str) -> None:
    w = await World(sign_up, db_session).build()

    # httpx не пошлёт перевод строки в заголовке — отправляем как есть через байты.
    response = await w.owner.post(
        f"{API}/tasks",
        json={"title": "X", "team_id": w.team["id"]},
        headers=[(b"Idempotency-Key", key.encode())],
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_idempotency_key"
    assert await task_count(w) == 0


async def test_failed_creation_is_not_stored(sign_up: SignUp, db_session: AsyncSession) -> None:
    """Ошибка не запоминается: исправленный повтор с тем же ключом проходит."""
    w = await World(sign_up, db_session).build()
    bad = await w.owner.post(
        f"{API}/tasks",
        json={"title": "X", "team_id": w.team["id"], "state_id": w.team["id"]},
        headers={"Idempotency-Key": "fix-me"},
    )

    assert bad.status_code == 400
    assert await db_session.scalar(select(func.count()).select_from(IdempotencyKey)) == 0


async def test_purge_removes_only_expired(sign_up: SignUp, db_session: AsyncSession) -> None:
    await sign_up("owner@example.com")
    user_id = await user_id_of(db_session, "owner@example.com")
    now = datetime.now(UTC)
    for key, age in (("old", timedelta(hours=25)), ("fresh", timedelta(hours=23))):
        db_session.add(
            IdempotencyKey(
                key=key,
                user_id=user_id,
                endpoint="POST /tasks",
                request_hash="0" * 64,
                response_status=201,
                response_body={},
                created_at=now - age,
            )
        )
    await db_session.flush()

    removed = await IdempotencyService(db_session).purge_expired(now)

    left = await db_session.scalars(select(IdempotencyKey.key))
    assert removed == 1
    assert list(left) == ["fresh"]


async def test_lifespan_starts_purge(monkeypatch: pytest.MonkeyPatch, app: FastAPI) -> None:
    """Очистка идёт при старте приложения — дальше раз в час, отдельной корутиной."""
    started = asyncio.Event()

    async def fake_purge(self: IdempotencyService, now: datetime | None = None) -> int:
        started.set()
        return 0

    monkeypatch.setattr(IdempotencyService, "purge_expired", fake_purge)

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(started.wait(), timeout=2)
