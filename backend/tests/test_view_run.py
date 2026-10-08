"""`GET /views/{id}/tasks`: фильтры, видимость читателя, сортировка, группы и их страницы."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.views.models import View
from tests.org import API, create_task, create_team, team_states
from tests.test_tasks import World

SignUp = Callable[..., Awaitable[AsyncClient]]


async def view(client: AsyncClient, w: World, scope: str = "user", **fields: Any) -> str:
    body: dict[str, Any] = {"workspace_id": w.workspace["id"], "scope": scope, "name": "Срез"}
    if scope == "team":
        body["team_id"] = w.team["id"]
    response = await client.post(f"{API}/views", json={**body, **fields})
    assert response.status_code == 201, response.text
    view_id: str = response.json()["id"]
    return view_id


async def run(client: AsyncClient, view_id: str, **params: Any) -> Any:
    response = await client.get(f"{API}/views/{view_id}/tasks", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def grouped_keys(result: Any) -> list[tuple[str | None, list[str]]]:
    return [(g["key"], [t["key"] for t in g["items"]]) for g in result["groups"]]


async def label(w: World, name: str) -> str:
    response = await w.owner.post(
        f"{API}/labels", json={"workspace_id": w.workspace["id"], "name": name, "color": "#ff0000"}
    )
    label_id: str = response.json()["id"]
    return label_id


async def test_scenario_v_my_open_bugs(sign_up: SignUp, db_session: AsyncSession) -> None:
    """Сценарий В: «Мои незакрытые баги» с группировкой по приоритету на доске —
    один сохранённый view, разный результат для двух людей благодаря `@me`."""
    w = await World(sign_up, db_session).build()
    dev, dev_id = await w.person("dev@example.com", workspace_role="member")
    qa, qa_id = await w.person("qa@example.com", workspace_role="member")
    bug = await label(w, "bug")
    feature = await label(w, "feature")
    done = w.states["Done"]["id"]
    await w.task(assignee_id=dev_id, label_ids=[bug], priority=2)  # ENG-1
    await w.task(assignee_id=dev_id, label_ids=[bug], priority=1)  # ENG-2
    await w.task(assignee_id=dev_id, label_ids=[bug])  # ENG-3 — без приоритета
    await w.task(assignee_id=dev_id, label_ids=[bug], state_id=done)  # ENG-4 — закрыта
    await w.task(assignee_id=dev_id, label_ids=[feature], priority=1)  # ENG-5 — не баг
    await w.task(assignee_id=qa_id, label_ids=[bug], priority=3)  # ENG-6 — чужая
    shared = await view(
        w.owner,
        w,
        "workspace",
        name="Мои незакрытые баги",
        filters={
            "assignee_id": {"op": "in", "value": ["@me"]},
            "label_id": {"op": "in", "value": [bug]},
            "state_type": {"op": "nin", "value": ["completed"]},
        },
        group_by="priority",
        layout="board",
    )

    for_dev = await run(dev, shared)
    for_qa = await run(qa, shared)

    assert for_dev["group_by"] == "priority"
    assert grouped_keys(for_dev) == [("1", ["ENG-2"]), ("2", ["ENG-1"]), ("0", ["ENG-3"])]
    assert grouped_keys(for_qa) == [("3", ["ENG-6"])]
    assert [g["count"] for g in for_dev["groups"]] == [1, 1, 1]


class TestUngrouped:
    async def test_single_group_in_manual_order(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        for _ in range(3):
            await w.task()
        await w.owner.post(f"{API}/tasks/ENG-3/move", json={"position": "top"})
        view_id = await view(w.owner, w)

        result = await run(w.owner, view_id)

        assert result["group_by"] is None
        assert grouped_keys(result) == [(None, ["ENG-3", "ENG-1", "ENG-2"])]
        assert result["groups"][0]["count"] == 3

    async def test_pages(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        for _ in range(5):
            await w.task()
        view_id = await view(w.owner, w, sort_by="created_at", sort_direction="desc")

        seen: list[str] = []
        cursor = None
        while True:
            params: dict[str, Any] = {"limit": 2}
            if cursor:
                params["cursor"] = cursor
            (group,) = (await run(w.owner, view_id, **params))["groups"]
            seen += [item["key"] for item in group["items"]]
            assert group["count"] == 5
            if not group["has_more"]:
                break
            cursor = group["next_cursor"]

        assert seen == ["ENG-5", "ENG-4", "ENG-3", "ENG-2", "ENG-1"]

    async def test_visibility_of_reader_applies(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        """Общий view не расширяет видимость: каждый видит в нём только своё."""
        w = await World(sign_up, db_session).build()
        secret = await create_team(w.owner, w.workspace["id"], key="SEC", is_private=True)
        await w.task()
        await create_task(w.owner, team_id=secret["id"])
        member, _ = await w.person("member@example.com", workspace_role="member")
        shared = await view(w.owner, w, "workspace")

        assert sorted(grouped_keys(await run(w.owner, shared))[0][1]) == ["ENG-1", "SEC-1"]
        assert grouped_keys(await run(member, shared)) == [(None, ["ENG-1"])]

    async def test_deleted_tasks_are_excluded(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        await w.task()
        await w.task()
        await w.owner.delete(f"{API}/tasks/ENG-1")

        assert grouped_keys(await run(w.owner, await view(w.owner, w))) == [(None, ["ENG-2"])]


class TestSorting:
    async def test_priority_puts_none_last(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        for priority in (0, 3, 1, 4):
            await w.task(priority=priority)
        asc = await view(w.owner, w, sort_by="priority")
        desc = await view(w.owner, w, sort_by="priority", sort_direction="desc")

        assert grouped_keys(await run(w.owner, asc))[0][1] == ["ENG-3", "ENG-2", "ENG-4", "ENG-1"]
        assert grouped_keys(await run(w.owner, desc))[0][1] == ["ENG-1", "ENG-4", "ENG-2", "ENG-3"]

    async def test_due_date_empty_last_both_ways(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        await w.task()
        await w.task(due_date="2026-10-20")
        await w.task(due_date="2026-10-10")
        asc = await view(w.owner, w, sort_by="due_date")
        desc = await view(w.owner, w, sort_by="due_date", sort_direction="desc")

        assert grouped_keys(await run(w.owner, asc))[0][1] == ["ENG-3", "ENG-2", "ENG-1"]
        assert grouped_keys(await run(w.owner, desc))[0][1] == ["ENG-2", "ENG-3", "ENG-1"]

    async def test_title_and_paging_across_equal_values(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        """Равные значения ключа — тай-брейк по id, страницы не теряют задач."""
        w = await World(sign_up, db_session).build()
        for title in ("Бета", "Альфа", "Альфа", "Альфа"):
            await w.task(title=title)
        view_id = await view(w.owner, w, sort_by="title")

        first = (await run(w.owner, view_id, limit=2))["groups"][0]
        second = (await run(w.owner, view_id, limit=2, cursor=first["next_cursor"]))["groups"][0]

        keys = [t["key"] for t in first["items"] + second["items"]]
        assert keys == ["ENG-2", "ENG-3", "ENG-4", "ENG-1"]

    async def test_cursor_of_other_sort_is_rejected(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        for _ in range(3):
            await w.task()
        view_id = await view(w.owner, w)
        cursor = (await run(w.owner, view_id, limit=1))["groups"][0]["next_cursor"]
        await w.owner.patch(f"{API}/views/{view_id}", json={"sort_by": "title"})

        response = await w.owner.get(f"{API}/views/{view_id}/tasks", params={"cursor": cursor})

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_cursor"


class TestGroups:
    async def test_by_state_in_type_order(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        states = await team_states(w.owner, w.team["id"])
        await w.task(state_id=states["Done"]["id"])
        await w.task(state_id=states["Backlog"]["id"])
        await w.task(state_id=states["In Progress"]["id"])
        await w.task()
        view_id = await view(w.owner, w, group_by="state")

        result = await run(w.owner, view_id)

        assert grouped_keys(result) == [
            (states["Backlog"]["id"], ["ENG-2"]),
            (states["Todo"]["id"], ["ENG-4"]),
            (states["In Progress"]["id"], ["ENG-3"]),
            (states["Done"]["id"], ["ENG-1"]),
        ]

    async def test_by_label_repeats_tasks(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        bug = await label(w, "bug")
        api = await label(w, "api")
        await w.task(label_ids=[bug, api])
        await w.task(label_ids=[bug])
        await w.task()
        view_id = await view(w.owner, w, group_by="label")

        result = await run(w.owner, view_id)

        assert grouped_keys(result) == [
            (api, ["ENG-1"]),
            (bug, ["ENG-1", "ENG-2"]),
            (None, ["ENG-3"]),
        ]

    async def test_by_assignee_and_project(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        _, anna = await w.person("anna@example.com", workspace_role="member")
        await w.task(assignee_id=anna)
        await create_task(w.owner, project_id=w.project["id"])
        await w.task()
        by_assignee = await view(w.owner, w, group_by="assignee")
        by_project = await view(w.owner, w, group_by="project")

        assert grouped_keys(await run(w.owner, by_assignee)) == [
            (anna, ["ENG-1"]),
            (None, ["ENG-2", "ENG-3"]),
        ]
        assert grouped_keys(await run(w.owner, by_project)) == [
            (w.project["id"], ["ENG-2"]),
            (None, ["ENG-1", "ENG-3"]),
        ]

    async def test_one_group_is_paged_separately(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        for _ in range(3):
            await w.task(priority=2)
        await w.task(due_date="2026-10-20")
        view_id = await view(w.owner, w, group_by="priority")

        overview = await run(w.owner, view_id, limit=2)
        high = overview["groups"][0]
        rest = await run(w.owner, view_id, limit=2, group="2", cursor=high["next_cursor"])
        no_priority = await run(w.owner, view_id, group="0")
        empty = await run(w.owner, view_id, group="1")

        assert (high["key"], high["count"], high["has_more"]) == ("2", 3, True)
        assert grouped_keys(rest) == [("2", ["ENG-3"])]
        assert rest["groups"][0]["has_more"] is False
        assert grouped_keys(no_priority) == [("0", ["ENG-4"])]
        # Пустая колонка доски — группа с нулём, а не пропажа группы.
        assert grouped_keys(empty) == [("1", [])]
        assert empty["groups"][0]["count"] == 0

    async def test_group_errors(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        await w.task()
        grouped = await view(w.owner, w, group_by="state")
        flat = await view(w.owner, w)
        cursor_like = "W10="

        for view_id, params in (
            (grouped, {"group": "not-a-uuid"}),
            (flat, {"group": "none"}),
            (grouped, {"cursor": cursor_like}),
        ):
            response = await w.owner.get(f"{API}/views/{view_id}/tasks", params=params)
            assert response.status_code == 400, params


class TestFilters:
    async def test_team_view_is_scoped_to_team(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        other = await create_team(w.owner, w.workspace["id"], key="DES", name="Дизайн")
        await w.task()
        await create_task(w.owner, team_id=other["id"])

        assert grouped_keys(await run(w.owner, await view(w.owner, w, "team"))) == [
            (None, ["ENG-1"])
        ]

    async def test_blocked_and_text_end_to_end(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        await w.task(title="Блокер")
        await w.task(title="Зависимая")
        await w.task(title="Свободная 100%")
        await w.owner.post(
            f"{API}/tasks/ENG-1/relations", json={"type": "blocks", "target_id": "ENG-2"}
        )
        blocked = await view(w.owner, w, filters={"is_blocked": {"op": "eq", "value": True}})
        percent = await view(w.owner, w, filters={"title": {"op": "contains", "value": "100%"}})

        assert grouped_keys(await run(w.owner, blocked)) == [(None, ["ENG-2"])]
        assert grouped_keys(await run(w.owner, percent)) == [(None, ["ENG-3"])]

        # Блокер закрыт — задача больше не заблокирована.
        await w.owner.patch(f"{API}/tasks/ENG-1", json={"state_id": w.states["Done"]["id"]})
        assert grouped_keys(await run(w.owner, blocked)) == [(None, [])]

    async def test_injection_payload_is_just_text(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        await w.task()
        payload = "'; DROP TABLE tasks; --"
        view_id = await view(w.owner, w, filters={"title": {"op": "contains", "value": payload}})

        assert grouped_keys(await run(w.owner, view_id)) == [(None, [])]
        assert (await w.owner.get(f"{API}/tasks/ENG-1")).status_code == 200

    async def test_dynamic_dates(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        today = datetime.now(UTC).date()
        await w.task(due_date=(today + timedelta(days=3)).isoformat())
        await w.task(due_date=(today + timedelta(days=30)).isoformat())
        await w.task()
        soon = await view(w.owner, w, filters={"due_date": {"op": "lte", "value": "@today+7d"}})

        assert grouped_keys(await run(w.owner, soon)) == [(None, ["ENG-1"])]

    async def test_stale_filter_is_400(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        """Сохранённый фильтр, переставший проходить грамматику, — внятная ошибка, не 500."""
        w = await World(sign_up, db_session).build()
        view_id = await view(w.owner, w)
        await db_session.execute(
            update(View)
            .where(View.id == UUID(view_id))
            .values(filters={"estimate": {"op": "eq", "value": 3}})
        )

        response = await w.owner.get(f"{API}/views/{view_id}/tasks")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_filter"
        assert response.json()["error"]["details"] == {"field": "estimate"}


async def query(client: AsyncClient, w: World, **body: Any) -> Any:
    return await client.post(f"{API}/views/query", json={"workspace_id": w.workspace["id"], **body})


class TestAdHocQuery:
    """`POST /views/query` — несохранённый view: та же грамматика, тот же транслятор."""

    async def test_filters_sort_and_pages(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        await w.task(title="Без приоритета")  # ENG-1
        await w.task(title="Срочная", priority=1)  # ENG-2
        await w.task(title="Низкая", priority=4)  # ENG-3
        await w.task(title="Высокая", priority=2, assignee_id=None)  # ENG-4
        body = {
            "filters": {"priority": {"op": "in", "value": [1, 2, 4]}},
            "sort_by": "priority",
            "limit": 2,
        }

        first = (await query(w.owner, w, **body)).json()
        (group,) = first["groups"]
        second = (await query(w.owner, w, **body, cursor=group["next_cursor"])).json()

        assert first["group_by"] is None and "view_id" not in first
        assert (group["key"], group["count"], group["has_more"]) == (None, 3, True)
        assert [t["key"] for t in group["items"]] == ["ENG-2", "ENG-4"]
        assert [t["key"] for t in second["groups"][0]["items"]] == ["ENG-3"]

    async def test_grouping_and_extended_grammar(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        _, dev_id = await w.person("dev@example.com", workspace_role="member")
        parent = await w.task(title="Родитель")  # ENG-1
        await w.task(title="Подзадача", parent_id=parent["id"])  # ENG-2
        await w.task(title="Чья-то", assignee_id=dev_id, priority=3)  # ENG-3

        unassigned = await query(
            w.owner, w, filters={"assignee_id": {"op": "is_null"}}, group_by="priority"
        )
        children = await query(w.owner, w, filters={"parent_id": {"op": "in", "value": ["ENG-1"]}})
        by_id = await query(
            w.owner, w, filters={"parent_id": {"op": "in", "value": [parent["id"]]}}
        )

        assert grouped_keys(unassigned.json()) == [("0", ["ENG-1", "ENG-2"])]
        assert children.status_code == 422
        assert [t["key"] for t in by_id.json()["groups"][0]["items"]] == ["ENG-2"]

    async def test_reader_visibility_and_read_token(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        secret = await create_team(w.owner, w.workspace["id"], key="SEC", is_private=True)
        await w.task(title="Открытая")
        await create_task(w.owner, team_id=secret["id"], title="Тайная")
        member, _ = await w.person("member@example.com", workspace_role="member")
        token = (
            await member.post(f"{API}/me/tokens", json={"name": "агент", "scope": "read"})
        ).json()["token"]

        response = await member.post(
            f"{API}/views/query",
            json={"workspace_id": w.workspace["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200, response.text
        assert [t["key"] for t in response.json()["groups"][0]["items"]] == ["ENG-1"]

    async def test_bad_definition_is_422(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()

        for body in (
            {"filters": {"asignee_id": {"op": "in", "value": ["@me"]}}},
            {"sort_by": "random"},
            {"group": "1"},
        ):
            response = await query(w.owner, w, **body)
            assert response.status_code in (400, 422), body
