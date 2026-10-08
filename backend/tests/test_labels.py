"""Метки уровня workspace и команды; замена набора меток задачи."""

from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.org import API, activity_types, create_task, create_team, create_workspace
from tests.test_tasks import World

SignUp = Callable[..., Awaitable[AsyncClient]]


async def label(w: World, name: str, team_id: str | None = None, **extra: Any) -> Any:
    body = {"workspace_id": w.workspace["id"], "name": name, "color": "#ff0000", **extra}
    if team_id:
        body["team_id"] = team_id
    return await w.owner.post(f"{API}/labels", json=body)


async def names(client: AsyncClient, **params: str) -> list[str]:
    response = await client.get(f"{API}/labels", params=params)
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


class TestCrud:
    async def test_names_unique_per_level(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()

        shared = await label(w, "bug")
        team_level = await label(w, "Bug", w.team["id"])
        clash = await label(w, "BUG")

        assert shared.status_code == 201
        assert team_level.status_code == 201
        assert clash.status_code == 409
        assert clash.json()["error"]["code"] == "label_name_taken"

    async def test_list_by_level(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        secret = await create_team(w.owner, w.workspace["id"], key="SEC", is_private=True)
        await label(w, "bug")
        await label(w, "backend", w.team["id"])
        await label(w, "тайна", secret["id"])
        member, _ = await w.person("member@example.com", workspace_role="member")
        ws = w.workspace["id"]

        assert await names(w.owner, workspace_id=ws) == ["bug", "backend", "тайна"]
        assert await names(member, workspace_id=ws) == ["bug", "backend"]
        assert await names(member, workspace_id=ws, team_id=w.team["id"]) == ["bug", "backend"]
        hidden = await member.get(
            f"{API}/labels", params={"workspace_id": ws, "team_id": secret["id"]}
        )
        assert hidden.status_code == 404

    async def test_contractor_reads_team_labels(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        await label(w, "backend", w.team["id"])
        contractor, _ = await w.person(
            "contractor@example.com",
            workspace_role="guest",
            project_id=w.project["id"],
            project_role="member",
        )

        assert await names(contractor, workspace_id=w.workspace["id"], team_id=w.team["id"]) == [
            "backend"
        ]

    async def test_update_and_delete(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await World(sign_up, db_session).build()
        created = (await label(w, "bug")).json()
        await label(w, "ui")
        task = await w.task(label_ids=[created["id"]])

        renamed = await w.owner.patch(f"{API}/labels/{created['id']}", json={"name": "defect"})
        clash = await w.owner.patch(f"{API}/labels/{created['id']}", json={"name": "UI"})
        deleted = await w.owner.delete(f"{API}/labels/{created['id']}")
        after = (await w.owner.get(f"{API}/tasks/{task['key']}")).json()

        assert renamed.json()["name"] == "defect"
        assert clash.status_code == 409
        assert deleted.status_code == 204
        assert after["label_ids"] == []

    async def test_team_of_other_workspace_is_404(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        other = await create_workspace(w.owner, slug="other", name="Other")

        response = await w.owner.post(
            f"{API}/labels",
            json={
                "workspace_id": other["id"],
                "team_id": w.team["id"],
                "name": "x",
                "color": "#000000",
            },
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "team_not_found"


class TestTaskLabels:
    async def test_replace_set_with_history(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        bug = (await label(w, "bug")).json()
        ui = (await label(w, "ui", w.team["id"])).json()
        task = await w.task(label_ids=[bug["id"]])
        url = f"{API}/tasks/{task['key']}/labels"

        replaced = await w.owner.put(url, json={"label_ids": [ui["id"]]})

        assert replaced.status_code == 200, replaced.text
        assert replaced.json()["label_ids"] == [ui["id"]]
        assert [item["name"] for item in replaced.json()["labels"]] == ["ui"]
        assert await activity_types(w.owner, task["key"]) == [
            "task_created",
            "label_added",
            "label_removed",
        ]

    async def test_other_team_label_is_rejected(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        design = await create_team(w.owner, w.workspace["id"], key="DES", name="Дизайн")
        foreign = (await label(w, "макет", design["id"])).json()
        task = await w.task()

        response = await w.owner.put(
            f"{API}/tasks/{task['key']}/labels", json={"label_ids": [foreign["id"]]}
        )
        on_create = await w.owner.post(
            f"{API}/tasks",
            json={"title": "X", "team_id": w.team["id"], "label_ids": [foreign["id"]]},
        )

        for bad in (response, on_create):
            assert bad.status_code == 400
            assert bad.json()["error"]["code"] == "label_not_applicable"
            assert bad.json()["error"]["details"]["label_ids"] == [foreign["id"]]

    async def test_label_of_other_workspace_is_rejected(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await World(sign_up, db_session).build()
        other = await create_workspace(w.owner, slug="other", name="Other")
        stranger_label = await w.owner.post(
            f"{API}/labels",
            json={"workspace_id": other["id"], "name": "чужая", "color": "#000000"},
        )
        task = await create_task(w.owner, team_id=w.team["id"])

        response = await w.owner.put(
            f"{API}/tasks/{task['key']}/labels",
            json={"label_ids": [stranger_label.json()["id"]]},
        )

        assert response.status_code == 400
