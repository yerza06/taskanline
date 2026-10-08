"""Список задач: видимость, фильтры, курсор, полнотекстовый поиск, expand."""

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.teams.models import TeamMember
from tests.org import API, create_project, create_task, create_team, team_states
from tests.test_tasks import World

SignUp = Callable[..., Awaitable[AsyncClient]]


async def keys(client: AsyncClient, workspace_id: str, **params: Any) -> list[str]:
    response = await client.get(f"{API}/tasks", params={"workspace_id": workspace_id, **params})
    assert response.status_code == 200, response.text
    return [item["key"] for item in response.json()["items"]]


class TestVisibility:
    async def test_list_matches_access(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        """Подрядчик видит только задачи своего проекта; участник — открытые команды."""
        w = await World(sign_up, db_session).build()
        secret = await create_team(w.owner, w.workspace["id"], key="SEC", is_private=True)
        await create_task(w.owner, project_id=w.project["id"])  # ENG-1
        await w.task()  # ENG-2 — бэклог команды
        await create_task(w.owner, team_id=secret["id"])  # SEC-1
        contractor, _ = await w.person(
            "contractor@example.com",
            workspace_role="guest",
            project_id=w.project["id"],
            project_role="viewer",
        )
        member, _ = await w.person("member@example.com", workspace_role="member")

        # Порядок общий только внутри команды: между командами ключи сортировки совпадают.
        assert sorted(await keys(w.owner, w.workspace["id"])) == ["ENG-1", "ENG-2", "SEC-1"]
        assert await keys(member, w.workspace["id"]) == ["ENG-1", "ENG-2"]
        assert await keys(contractor, w.workspace["id"]) == ["ENG-1"]

    async def test_stranger_gets_404(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        stranger, _ = await w.person("stranger@example.com")

        response = await stranger.get(f"{API}/tasks", params={"workspace_id": w.workspace["id"]})

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "workspace_not_found"


class TestFilters:
    async def test_by_fields(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        dev, dev_id = await w.person("dev@example.com", workspace_role="member")
        other = await create_project(w.owner, w.team["id"], name="Другой")
        await create_task(w.owner, project_id=w.project["id"], assignee_id=dev_id, priority=1)
        await w.task(state_id=w.states["In Progress"]["id"], due_date="2026-10-10")
        await create_task(w.owner, project_id=other["id"], priority=4, due_date="2026-11-01")
        ws = w.workspace["id"]

        assert await keys(w.owner, ws, project_id=w.project["id"]) == ["ENG-1"]
        assert await keys(w.owner, ws, project_id=[w.project["id"], other["id"]]) == [
            "ENG-1",
            "ENG-3",
        ]
        assert await keys(w.owner, ws, state_type="started") == ["ENG-2"]
        assert await keys(w.owner, ws, state_type=["started", "unstarted"]) == [
            "ENG-1",
            "ENG-2",
            "ENG-3",
        ]
        assert await keys(dev, ws, assignee_id="me") == ["ENG-1"]
        assert await keys(w.owner, ws, assignee_id="none") == ["ENG-2", "ENG-3"]
        assert await keys(w.owner, ws, assignee_id=["none", dev_id]) == ["ENG-1", "ENG-2", "ENG-3"]
        assert await keys(w.owner, ws, creator_id="me") == ["ENG-1", "ENG-2", "ENG-3"]
        assert await keys(dev, ws, creator_id="me") == []
        assert await keys(w.owner, ws, priority=[1, 4]) == ["ENG-1", "ENG-3"]
        assert await keys(w.owner, ws, due_before="2026-10-31") == ["ENG-2"]
        assert await keys(w.owner, ws, due_after="2026-10-31") == ["ENG-3"]
        assert await keys(w.owner, ws, team_id=w.team["id"]) == ["ENG-1", "ENG-2", "ENG-3"]

    async def test_by_label_and_parent(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        label = await w.owner.post(
            f"{API}/labels",
            json={"workspace_id": w.workspace["id"], "name": "bug", "color": "#ff0000"},
        )
        parent = await w.task(label_ids=[label.json()["id"]])
        await w.task(parent_id=parent["key"])
        ws = w.workspace["id"]

        assert await keys(w.owner, ws, label_id=label.json()["id"]) == ["ENG-1"]
        assert await keys(w.owner, ws, parent_id=parent["id"]) == ["ENG-2"]

    async def test_bad_filter_values(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        ws = w.workspace["id"]

        for params in ({"assignee_id": "someone"}, {"creator_id": "none"}, {"priority": 9}):
            response = await w.owner.get(f"{API}/tasks", params={"workspace_id": ws, **params})
            assert response.status_code == 400, params
            assert response.json()["error"]["code"] == "invalid_filter"
        bad_type = await w.owner.get(
            f"{API}/tasks", params={"workspace_id": ws, "state_type": "done"}
        )
        assert bad_type.status_code == 422

    async def test_deleted_only_on_request(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        await w.task()
        doomed = await w.task()
        await w.owner.delete(f"{API}/tasks/{doomed['key']}")

        assert await keys(w.owner, w.workspace["id"]) == ["ENG-1"]
        assert await keys(w.owner, w.workspace["id"], deleted="true") == ["ENG-2"]


class TestSearch:
    async def test_title_and_description(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        await w.task(title="Починить редирект после логина")
        await w.task(title="Обновить зависимости", description="Редирект тоже проверить")
        await w.task(title="Сделать отчёт")
        ws = w.workspace["id"]

        assert await keys(w.owner, ws, q="редирект") == ["ENG-1", "ENG-2"]
        assert await keys(w.owner, ws, q="логина") == ["ENG-1"]
        assert await keys(w.owner, ws, q="редирект -логина") == ["ENG-2"]
        assert await keys(w.owner, ws, q="  ") == ["ENG-1", "ENG-2", "ENG-3"]


class TestPagination:
    async def test_pages_follow_cursor(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        for _ in range(5):
            await w.task()

        seen: list[str] = []
        cursor = None
        while True:
            params: dict[str, Any] = {"workspace_id": w.workspace["id"], "limit": 2}
            if cursor:
                params["cursor"] = cursor
            page = (await w.owner.get(f"{API}/tasks", params=params)).json()
            seen += [item["key"] for item in page["items"]]
            if not page["has_more"]:
                assert page["next_cursor"] is None
                break
            cursor = page["next_cursor"]

        assert seen == ["ENG-1", "ENG-2", "ENG-3", "ENG-4", "ENG-5"]

    async def test_insert_before_cursor_neither_duplicates_nor_skips(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        """Перестановка вперёд уже выданной страницы не сдвигает следующую."""
        w = await World(sign_up, db_session).build()
        for _ in range(4):
            await w.task()
        ws = w.workspace["id"]

        first = (await w.owner.get(f"{API}/tasks", params={"workspace_id": ws, "limit": 2})).json()
        await w.task()  # ENG-5 — в конец
        await w.owner.post(f"{API}/tasks/ENG-5/move", json={"position": "top"})
        second = (
            await w.owner.get(
                f"{API}/tasks",
                params={"workspace_id": ws, "limit": 10, "cursor": first["next_cursor"]},
            )
        ).json()

        assert [item["key"] for item in first["items"]] == ["ENG-1", "ENG-2"]
        assert [item["key"] for item in second["items"]] == ["ENG-3", "ENG-4"]

    async def test_garbage_cursor(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()

        response = await w.owner.get(
            f"{API}/tasks", params={"workspace_id": w.workspace["id"], "cursor": "!!!"}
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_cursor"


class TestExpand:
    async def test_expand_in_list(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        _, dev_id = await w.person("dev@example.com", workspace_role="member")
        parent = await w.task()
        await w.task(assignee_id=dev_id, parent_id=parent["key"])

        page = (
            await w.owner.get(
                f"{API}/tasks",
                params={"workspace_id": w.workspace["id"], "expand": "assignee,state,parent"},
            )
        ).json()
        relations = await w.owner.get(
            f"{API}/tasks", params={"workspace_id": w.workspace["id"], "expand": "relations"}
        )

        child = page["items"][1]
        assert child["assignee"]["email"] == "dev@example.com"
        assert child["state"]["type"] == "unstarted"
        assert child["parent"] == {"id": parent["id"], "key": "ENG-1", "title": parent["title"]}
        assert page["items"][0]["assignee"] is None
        assert relations.status_code == 400

    async def test_parent_hidden_from_viewer_is_not_expanded(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        """Родитель из невидимой читателю части команды не раскрывается."""
        w = await World(sign_up, db_session).build()
        parent = await w.task(title="Секретный план")
        child = await create_task(w.owner, project_id=w.project["id"], parent_id=parent["key"])
        contractor, _ = await w.person(
            "contractor@example.com",
            workspace_role="guest",
            project_id=w.project["id"],
            project_role="viewer",
        )

        body = (await contractor.get(f"{API}/tasks/{child['key']}?expand=parent")).json()

        assert body["parent_id"] == parent["id"]
        assert body["parent"] is None


async def test_list_is_in_manual_order(sign_up: SignUp, db_session: AsyncSession) -> None:
    w = await World(sign_up, db_session).build()
    for _ in range(3):
        await w.task()
    await w.owner.post(f"{API}/tasks/ENG-3/move", json={"before_id": "ENG-1"})

    assert await keys(w.owner, w.workspace["id"]) == ["ENG-3", "ENG-1", "ENG-2"]


async def test_states_are_shared_by_board(sign_up: SignUp, db_session: AsyncSession) -> None:
    """Доска: колонки — статусы, внутри колонки порядок общий для команды."""
    w = await World(sign_up, db_session).build()
    states = await team_states(w.owner, w.team["id"])
    for _ in range(3):
        await w.task(state_id=states["In Progress"]["id"])
    await w.task()
    await w.owner.post(f"{API}/tasks/ENG-4/move", json={"after_id": "ENG-1"})

    in_progress = await keys(w.owner, w.workspace["id"], state_id=states["In Progress"]["id"])
    assert in_progress == ["ENG-1", "ENG-2", "ENG-3"]
    assert await keys(w.owner, w.workspace["id"]) == ["ENG-1", "ENG-4", "ENG-2", "ENG-3"]


async def test_guest_list_shows_team_membership_tasks(
    sign_up: SignUp, db_session: AsyncSession
) -> None:
    w = await World(sign_up, db_session).build()
    await w.task()
    guest, guest_id = await w.person("guest@example.com", workspace_role="guest")
    assert await keys(guest, w.workspace["id"]) == []

    db_session.add(
        TeamMember(
            workspace_id=UUID(w.workspace["id"]),
            team_id=UUID(w.team["id"]),
            user_id=UUID(guest_id),
            role="member",
        )
    )
    await db_session.flush()

    assert await keys(guest, w.workspace["id"]) == ["ENG-1"]
