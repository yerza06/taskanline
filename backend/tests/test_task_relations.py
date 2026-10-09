"""Подзадачи (цикл, глубина) и связи (одно направление, `blocked_by`, цикл блокировок)."""

from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.org import API, activity_types, create_task, create_team
from tests.test_tasks import World

SignUp = Callable[..., Awaitable[AsyncClient]]


async def link(w: World, key: str, kind: str, target: str) -> Any:
    return await w.owner.post(
        f"{API}/tasks/{key}/relations", json={"type": kind, "target_id": target}
    )


async def relations(w: World, key: str) -> list[tuple[str, str]]:
    body = (await w.owner.get(f"{API}/tasks/{key}", params={"expand": "relations"})).json()
    return [(item["type"], item["task"]["key"]) for item in body["relations"]]


class TestSubtasks:
    async def test_children_listed(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        parent = await w.task()
        await w.task(parent_id="ENG-1")
        await w.task(parent_id=parent["id"])

        response = await w.owner.get(f"{API}/tasks/ENG-1/subtasks")

        assert [item["key"] for item in response.json()["items"]] == ["ENG-2", "ENG-3"]

    async def test_cycle_is_rejected(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        await w.task()
        await w.task(parent_id="ENG-1")
        await w.task(parent_id="ENG-2")

        to_self = await w.owner.patch(f"{API}/tasks/ENG-1", json={"parent_id": "ENG-1"})
        to_grandchild = await w.owner.patch(f"{API}/tasks/ENG-1", json={"parent_id": "ENG-3"})

        for response in (to_self, to_grandchild):
            assert response.status_code == 400
            assert response.json()["error"]["code"] == "parent_cycle"

    async def test_depth_is_limited_to_five(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        await w.task()
        for level in range(2, 6):
            await w.task(parent_id=f"ENG-{level - 1}")

        sixth = await w.owner.post(
            f"{API}/tasks", json={"title": "Шестой", "team_id": w.team["id"], "parent_id": "ENG-5"}
        )
        # Поддерево из двух уровней под четвёртым — тоже шесть.
        await w.task()  # ENG-6
        await w.task(parent_id="ENG-6")  # ENG-7
        subtree = await w.owner.patch(f"{API}/tasks/ENG-6", json={"parent_id": "ENG-4"})
        fits = await w.owner.patch(f"{API}/tasks/ENG-6", json={"parent_id": "ENG-3"})

        for response in (sixth, subtree):
            assert response.status_code == 400
            assert response.json()["error"]["code"] == "parent_depth_exceeded"
        assert fits.status_code == 200, fits.text

    async def test_parent_change_history_and_clear(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        await w.task()
        await w.task()

        await w.owner.patch(f"{API}/tasks/ENG-2", json={"parent_id": "ENG-1"})
        cleared = await w.owner.patch(f"{API}/tasks/ENG-2", json={"parent_id": None})

        assert cleared.json()["parent_id"] is None
        assert await activity_types(w.owner, "ENG-2") == [
            "task_created",
            "parent_changed",
            "parent_changed",
        ]

    async def test_parent_in_other_team_of_same_workspace(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        design = await create_team(w.owner, w.workspace["id"], key="DES", name="Дизайн")
        await create_task(w.owner, team_id=design["id"])

        child = await w.task(parent_id="DES-1")

        assert child["parent_id"] is not None

    async def test_invisible_parent_is_not_found(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        await w.task()  # бэклог: подрядчику не виден
        contractor, _ = await w.person(
            "contractor@example.com",
            workspace_role="guest",
            project_id=w.project["id"],
            project_role="member",
        )

        response = await contractor.post(
            f"{API}/tasks",
            json={"title": "X", "project_id": w.project["id"], "parent_id": "ENG-1"},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "parent_not_found"


class TestRelations:
    async def test_blocked_by_is_blocks_read_backwards(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        await w.task()
        await w.task()

        created = await link(w, "ENG-2", "blocked_by", "ENG-1")

        assert created.status_code == 201, created.text
        assert created.json()["type"] == "blocked_by"
        assert created.json()["task"]["key"] == "ENG-1"
        assert await relations(w, "ENG-1") == [("blocks", "ENG-2")]
        assert await relations(w, "ENG-2") == [("blocked_by", "ENG-1")]
        assert (await activity_types(w.owner, "ENG-1"))[-1] == "relation_added"
        assert (await activity_types(w.owner, "ENG-2"))[-1] == "relation_added"

    async def test_duplicates_and_relates(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        for _ in range(3):
            await w.task()

        await link(w, "ENG-1", "duplicated_by", "ENG-2")
        await link(w, "ENG-1", "relates_to", "ENG-3")
        mirrored = await link(w, "ENG-3", "relates_to", "ENG-1")

        assert await relations(w, "ENG-2") == [("duplicates", "ENG-1")]
        assert await relations(w, "ENG-3") == [("relates_to", "ENG-1")]
        assert mirrored.status_code == 409
        assert mirrored.json()["error"]["code"] == "relation_exists"

    async def test_cycle_is_400(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        for _ in range(3):
            await w.task()
        await link(w, "ENG-1", "blocks", "ENG-2")
        await link(w, "ENG-2", "blocks", "ENG-3")

        direct = await link(w, "ENG-2", "blocks", "ENG-1")
        transitive = await link(w, "ENG-3", "blocks", "ENG-1")
        # Цикл через перевёрнутую связь: «1 заблокирована 3-й» — это «3 блокирует 1».
        inverted = await link(w, "ENG-1", "blocked_by", "ENG-3")

        for response in (direct, transitive, inverted):
            assert response.status_code == 400, response.text
            assert response.json()["error"]["code"] == "relation_cycle"

    async def test_duplicate_and_self(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        await w.task()
        await w.task()
        await link(w, "ENG-1", "blocks", "ENG-2")

        again = await link(w, "ENG-2", "blocked_by", "ENG-1")
        itself = await link(w, "ENG-1", "relates_to", "ENG-1")
        missing = await link(w, "ENG-1", "relates_to", "ENG-99")

        assert again.status_code == 409
        assert itself.json()["error"]["code"] == "relation_self"
        assert missing.json()["error"]["code"] == "target_not_found"

    async def test_remove_from_either_end(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        for _ in range(3):
            await w.task()
        relation = (await link(w, "ENG-1", "blocks", "ENG-2")).json()

        stranger_task = await w.owner.delete(f"{API}/tasks/ENG-3/relations/{relation['id']}")
        removed = await w.owner.delete(f"{API}/tasks/ENG-2/relations/{relation['id']}")

        assert stranger_task.status_code == 404
        assert stranger_task.json()["error"]["code"] == "relation_not_found"
        assert removed.status_code == 204
        assert await relations(w, "ENG-1") == []
        assert (await activity_types(w.owner, "ENG-1"))[-1] == "relation_removed"

    async def test_hidden_related_task_is_not_shown(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        await create_task(w.owner, project_id=w.project["id"])  # ENG-1
        await w.task(title="Секрет")  # ENG-2 — бэклог
        await link(w, "ENG-1", "blocked_by", "ENG-2")
        contractor, _ = await w.person(
            "contractor@example.com",
            workspace_role="guest",
            project_id=w.project["id"],
            project_role="viewer",
        )

        body = (await contractor.get(f"{API}/tasks/ENG-1", params={"expand": "relations"})).json()

        assert body["relations"] == []
