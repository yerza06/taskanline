"""`POST /tasks/{id}/move`: перестановка и смена статуса одним вызовом."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.models import Task
from tests.org import API, activity_types, create_task, create_team
from tests.test_task_list import keys
from tests.test_tasks import World

SignUp = Callable[..., Awaitable[AsyncClient]]


async def built(sign_up: SignUp, session: AsyncSession, count: int = 3) -> World:
    w = await World(sign_up, session).build()
    for _ in range(count):
        await w.task()
    return w


async def move(w: World, key: str, **body: str) -> dict[str, object]:
    response = await w.owner.post(f"{API}/tasks/{key}/move", json=body)
    assert response.status_code == 200, response.text
    result: dict[str, object] = response.json()
    return result


class TestPlacement:
    async def test_top_bottom_after_before(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await built(sign_up, db_session, 4)
        ws = w.workspace["id"]

        await move(w, "ENG-4", position="top")
        assert await keys(w.owner, ws) == ["ENG-4", "ENG-1", "ENG-2", "ENG-3"]
        await move(w, "ENG-4", position="bottom")
        assert await keys(w.owner, ws) == ["ENG-1", "ENG-2", "ENG-3", "ENG-4"]
        await move(w, "ENG-1", after_id="ENG-3")
        assert await keys(w.owner, ws) == ["ENG-2", "ENG-3", "ENG-1", "ENG-4"]
        await move(w, "ENG-4", before_id="eng-2")
        assert await keys(w.owner, ws) == ["ENG-4", "ENG-2", "ENG-3", "ENG-1"]

    async def test_state_and_place_in_one_call(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await built(sign_up, db_session)

        body = await move(w, "ENG-3", state_id=w.states["In Progress"]["id"], position="top")

        assert body["state_id"] == w.states["In Progress"]["id"]
        assert body["started_at"] is not None
        assert await keys(w.owner, w.workspace["id"]) == ["ENG-3", "ENG-1", "ENG-2"]
        assert (await activity_types(w.owner, "ENG-3"))[-2:] == ["state_changed", "task_moved"]

    async def test_same_place_writes_no_history(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await built(sign_up, db_session)

        await move(w, "ENG-2", after_id="ENG-1")  # уже на месте
        await move(w, "ENG-3", after_id="ENG-1")
        await move(w, "ENG-3", after_id="ENG-1")  # повтор

        assert await activity_types(w.owner, "ENG-2") == ["task_created"]
        assert await activity_types(w.owner, "ENG-3") == ["task_created", "task_moved"]

    async def test_invalid_requests(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await built(sign_up, db_session)
        other = await create_team(w.owner, w.workspace["id"], key="DES", name="Дизайн")
        await create_task(w.owner, team_id=other["id"])
        url = f"{API}/tasks/ENG-1/move"

        nothing = await w.owner.post(url, json={})
        two = await w.owner.post(url, json={"after_id": "ENG-2", "position": "top"})
        foreign = await w.owner.post(url, json={"after_id": "DES-1"})
        itself = await w.owner.post(url, json={"before_id": "ENG-1"})
        missing = await w.owner.post(url, json={"after_id": "ENG-99"})

        assert nothing.status_code == 422
        assert two.status_code == 422
        for response in (foreign, itself, missing):
            assert response.status_code == 400, response.text
            assert response.json()["error"]["code"] == "invalid_move_anchor"


class TestRebalance:
    async def test_long_keys_are_regenerated(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        """Ключ длиннее 32 символов запускает перегенерацию ключей всей команды."""
        w = await built(sign_up, db_session)
        rows = (
            await db_session.scalars(
                select(Task).where(Task.team_id == UUID(w.team["id"])).order_by(Task.number)
            )
        ).all()
        rows[0].sort_order = "a0" + "0" * 30 + "1"
        rows[1].sort_order = "a0" + "0" * 30 + "2"
        await db_session.flush()

        await move(w, "ENG-3", after_id="ENG-1")

        orders = list(
            await db_session.scalars(
                select(Task.sort_order).where(Task.team_id == UUID(w.team["id"]))
            )
        )
        assert max(len(order) for order in orders) <= 4
        assert await keys(w.owner, w.workspace["id"]) == ["ENG-1", "ENG-3", "ENG-2"]

    async def test_equal_keys_are_resolved(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        """Совпавшие ключи соседей (след гонки двух перестановок) не ломают вставку."""
        w = await built(sign_up, db_session)
        rows = (
            await db_session.scalars(
                select(Task).where(Task.team_id == UUID(w.team["id"])).order_by(Task.number)
            )
        ).all()
        rows[0].sort_order = rows[1].sort_order = "a5"
        await db_session.flush()

        await move(w, "ENG-3", after_id="ENG-1")

        assert await keys(w.owner, w.workspace["id"]) == ["ENG-1", "ENG-3", "ENG-2"]
