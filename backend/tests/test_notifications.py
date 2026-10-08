"""Входящие уведомления: только свои, непрочитанные отдельно, отметка о прочтении."""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.org import API
from tests.test_tasks import World

SignUp = Callable[..., Awaitable[AsyncClient]]


async def assigned_world(
    sign_up: SignUp, session: AsyncSession, count: int
) -> tuple[World, AsyncClient]:
    w = await World(sign_up, session).build()
    dev, dev_id = await w.person("dev@example.com", workspace_role="member")
    for _ in range(count):
        await w.task(assignee_id=dev_id)
    return w, dev


async def test_newest_first_with_cursor(sign_up: SignUp, db_session: AsyncSession) -> None:
    _, dev = await assigned_world(sign_up, db_session, 3)

    first = (await dev.get(f"{API}/me/notifications", params={"limit": 2})).json()
    second = (
        await dev.get(
            f"{API}/me/notifications", params={"limit": 2, "cursor": first["next_cursor"]}
        )
    ).json()

    created = [item["created_at"] for item in first["items"] + second["items"]]
    assert len(created) == 3
    assert created == sorted(created, reverse=True)
    assert (first["has_more"], second["has_more"]) == (True, False)


async def test_mark_read_and_unread_filter(sign_up: SignUp, db_session: AsyncSession) -> None:
    _, dev = await assigned_world(sign_up, db_session, 2)
    items = (await dev.get(f"{API}/me/notifications")).json()["items"]

    read = await dev.post(f"{API}/me/notifications/{items[0]['id']}/read")
    again = await dev.post(f"{API}/me/notifications/{items[0]['id']}/read")
    unread = (await dev.get(f"{API}/me/notifications", params={"unread": "true"})).json()

    assert read.status_code == 200
    assert read.json()["read_at"] is not None
    assert again.json()["read_at"] == read.json()["read_at"]
    assert [item["id"] for item in unread["items"]] == [items[1]["id"]]


async def test_foreign_notification_is_404(sign_up: SignUp, db_session: AsyncSession) -> None:
    w, dev = await assigned_world(sign_up, db_session, 1)
    notification = (await dev.get(f"{API}/me/notifications")).json()["items"][0]

    response = await w.owner.post(f"{API}/me/notifications/{notification['id']}/read")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "notification_not_found"


async def test_read_token_cannot_mark(sign_up: SignUp, db_session: AsyncSession) -> None:
    _, dev = await assigned_world(sign_up, db_session, 1)
    notification = (await dev.get(f"{API}/me/notifications")).json()["items"][0]
    token = (await dev.post(f"{API}/me/tokens", json={"name": "reader"})).json()["token"]

    listed = await dev.get(f"{API}/me/notifications", headers={"Authorization": f"Bearer {token}"})
    marked = await dev.post(
        f"{API}/me/notifications/{notification['id']}/read",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert listed.status_code == 200
    assert marked.status_code == 403
    assert marked.json()["error"]["code"] == "insufficient_scope"


async def test_reassignment_notifies_new_assignee(
    sign_up: SignUp, db_session: AsyncSession
) -> None:
    w = await World(sign_up, db_session).build()
    _, dev_id = await w.person("dev@example.com", workspace_role="member")
    qa, qa_id = await w.person("qa@example.com", workspace_role="member")
    task = await w.task(assignee_id=dev_id)

    await w.owner.patch(f"{API}/tasks/{task['key']}", json={"assignee_id": qa_id})

    items = (await qa.get(f"{API}/me/notifications")).json()["items"]
    assert [(item["type"], item["task_id"]) for item in items] == [("assigned", task["id"])]
