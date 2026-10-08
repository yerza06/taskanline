"""Комментарии: один уровень ответов, @упоминания, правка автором, удаление автором или admin."""

from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.org import API, activity_types, create_task
from tests.test_tasks import World

SignUp = Callable[..., Awaitable[AsyncClient]]


async def comment(client: AsyncClient, key: str, body: str, **extra: Any) -> Any:
    return await client.post(f"{API}/tasks/{key}/comments", json={"body": body, **extra})


async def inbox(client: AsyncClient) -> list[tuple[str, str | None]]:
    items = (await client.get(f"{API}/me/notifications")).json()["items"]
    return [(item["type"], item["comment_id"]) for item in items]


class TestCreate:
    async def test_comment_and_reply(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        task = await w.task()

        top = await comment(w.owner, task["key"], "Начнём?")
        reply = await comment(w.owner, task["key"], "Да", parent_id=top.json()["id"])
        nested = await comment(w.owner, task["key"], "Глубже", parent_id=reply.json()["id"])
        listed = (await w.owner.get(f"{API}/tasks/{task['key']}/comments")).json()

        assert top.status_code == 201, top.text
        assert reply.json()["parent_id"] == top.json()["id"]
        assert nested.status_code == 400
        assert nested.json()["error"]["code"] == "comment_reply_depth"
        assert [item["body"] for item in listed["items"]] == ["Начнём?", "Да"]
        assert await activity_types(w.owner, task["key"]) == [
            "task_created",
            "commented",
            "commented",
        ]

    async def test_parent_from_other_task_is_400(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        first = await w.task()
        second = await w.task()
        top = await comment(w.owner, first["key"], "Тут")

        response = await comment(w.owner, second["key"], "Там", parent_id=top.json()["id"])

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_parent_comment"

    async def test_viewer_cannot_comment(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        task = await create_task(w.owner, project_id=w.project["id"])
        viewer, _ = await w.person(
            "viewer@example.com",
            workspace_role="guest",
            project_id=w.project["id"],
            project_role="viewer",
        )

        read = await viewer.get(f"{API}/tasks/{task['key']}/comments")
        write = await comment(viewer, task["key"], "Можно?")

        assert read.status_code == 200
        assert write.status_code == 403

    async def test_agent_comment_keeps_token(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        task = await w.task()
        token = (
            await w.owner.post(
                f"{API}/me/tokens", json={"name": "claude-code", "scope": "read_write"}
            )
        ).json()
        agent_headers = {"Authorization": f"Bearer {token['token']}"}

        created = await w.owner.post(
            f"{API}/tasks/{task['key']}/comments",
            json={"body": "Исправлено в PR #218"},
            headers=agent_headers,
        )
        history = (await w.owner.get(f"{API}/tasks/{task['key']}/activities")).json()["items"]

        assert created.json()["author_token_id"] == token["id"]
        assert history[0]["type"] == "commented"
        assert history[0]["actor_token_id"] == token["id"]


class TestMentions:
    async def test_mention_notifies_once_and_skips_outsiders(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        task = await w.task()
        dev, dev_id = await w.person("dev@example.com", workspace_role="member")
        guest, _ = await w.person("guest@example.com", workspace_role="guest")
        stranger, _ = await w.person("stranger@example.com")

        created = await comment(
            w.owner,
            task["key"],
            "@DEV@example.com глянь, и @dev@example.com ещё раз. "
            "@guest@example.com, @stranger@example.com, @nobody@example.com, @owner@example.com",
        )

        assert created.json()["mention_ids"] == [dev_id]
        assert await inbox(dev) == [("mentioned", created.json()["id"])]
        assert await inbox(guest) == []
        assert await inbox(stranger) == []
        assert await inbox(w.owner) == []

    async def test_edit_notifies_only_new_mentions(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        task = await w.task()
        dev, dev_id = await w.person("dev@example.com", workspace_role="member")
        qa, qa_id = await w.person("qa@example.com", workspace_role="member")
        created = (await comment(w.owner, task["key"], "@dev@example.com")).json()

        edited = await w.owner.patch(
            f"{API}/comments/{created['id']}", json={"body": "@dev@example.com @qa@example.com"}
        )

        assert sorted(edited.json()["mention_ids"]) == sorted([dev_id, qa_id])
        assert len(await inbox(dev)) == 1
        assert len(await inbox(qa)) == 1


class TestEditAndDelete:
    async def test_only_author_edits(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        task = await w.task()
        member, _ = await w.person("member@example.com", workspace_role="member")
        mine = (await comment(member, task["key"], "Моё")).json()

        by_owner = await w.owner.patch(f"{API}/comments/{mine['id']}", json={"body": "Чужое"})
        by_author = await member.patch(f"{API}/comments/{mine['id']}", json={"body": "Исправил"})

        assert by_owner.status_code == 403
        assert by_owner.json()["error"]["code"] == "not_comment_author"
        assert by_author.json()["body"] == "Исправил"

    async def test_delete_by_author_or_admin(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        task = await w.task()
        alice, _ = await w.person("alice@example.com", workspace_role="member")
        bob, _ = await w.person("bob@example.com", workspace_role="member")
        first = (await comment(alice, task["key"], "Раз")).json()
        second = (await comment(alice, task["key"], "Два")).json()

        by_peer = await bob.delete(f"{API}/comments/{first['id']}")
        by_author = await alice.delete(f"{API}/comments/{first['id']}")
        by_admin = await w.owner.delete(f"{API}/comments/{second['id']}")
        again = await alice.delete(f"{API}/comments/{first['id']}")
        listed = (await w.owner.get(f"{API}/tasks/{task['key']}/comments")).json()["items"]

        assert by_peer.status_code == 403
        assert by_peer.json()["error"]["code"] == "insufficient_role"
        assert (by_author.status_code, by_admin.status_code) == (204, 204)
        assert again.status_code == 404
        assert listed == []

    async def test_outsider_and_read_token(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        task = await w.task()
        mine = (await comment(w.owner, task["key"], "Моё")).json()
        stranger, _ = await w.person("stranger@example.com")
        token = (
            await w.owner.post(f"{API}/me/tokens", json={"name": "reader", "scope": "read"})
        ).json()
        reader = {"Authorization": f"Bearer {token['token']}"}

        hidden = await stranger.patch(f"{API}/comments/{mine['id']}", json={"body": "x"})
        read_only = await w.owner.patch(
            f"{API}/comments/{mine['id']}", json={"body": "x"}, headers=reader
        )
        read_only_delete = await w.owner.delete(f"{API}/comments/{mine['id']}", headers=reader)

        assert hidden.status_code == 404
        assert hidden.json()["error"]["code"] == "comment_not_found"
        assert read_only.json()["error"]["code"] == "insufficient_scope"
        assert read_only_delete.json()["error"]["code"] == "insufficient_scope"

    async def test_comments_of_deleted_task_are_hidden(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        task = await w.task()
        mine = (await comment(w.owner, task["key"], "Моё")).json()
        await w.owner.delete(f"{API}/tasks/{task['key']}")

        listed = await w.owner.get(f"{API}/tasks/{task['key']}/comments")
        edited = await w.owner.patch(f"{API}/comments/{mine['id']}", json={"body": "x"})

        assert listed.status_code == 404
        assert edited.status_code == 404
