"""Задачи: создание, ключ ENG-142, изменение, удаление и восстановление."""

from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.org import (
    API,
    activity_types,
    create_project,
    create_task,
    create_team,
    create_workspace,
    grant,
    team_states,
    user_id_of,
)

SignUp = Callable[..., Awaitable[AsyncClient]]


class World:
    """Владелец, пространство `acme`, команда ENG с проектом и её статусы."""

    owner: AsyncClient
    workspace: dict[str, Any]
    team: dict[str, Any]
    project: dict[str, Any]
    states: dict[str, dict[str, Any]]

    def __init__(self, sign_up: SignUp, session: AsyncSession) -> None:
        self._sign_up = sign_up
        self._session = session

    async def build(self) -> "World":
        self.owner = await self._sign_up("owner@example.com", "Владелец")
        self.workspace = await create_workspace(self.owner)
        self.team = await create_team(self.owner, self.workspace["id"])
        self.project = await create_project(self.owner, self.team["id"])
        self.states = await team_states(self.owner, self.team["id"])
        return self

    async def person(self, email: str, **roles: Any) -> tuple[AsyncClient, str]:
        client = await self._sign_up(email)
        user_id = await user_id_of(self._session, email)
        if roles:
            await grant(self._session, user_id=user_id, workspace_id=self.workspace["id"], **roles)
        return client, str(user_id)

    async def task(self, **fields: Any) -> dict[str, Any]:
        return await create_task(self.owner, team_id=self.team["id"], **fields)


async def world(sign_up: SignUp, session: AsyncSession) -> World:
    return await World(sign_up, session).build()


class TestCreate:
    async def test_numbers_and_keys(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await world(sign_up, db_session)

        first = await w.task(title="Первая")
        second = await w.task(title="Вторая")

        assert (first["key"], first["number"]) == ("ENG-1", 1)
        assert (second["key"], second["number"]) == ("ENG-2", 2)
        assert first["state_id"] == w.states["Todo"]["id"]
        assert first["sort_order"] < second["sort_order"]
        assert first["label_ids"] == []
        assert "assignee" not in first

    async def test_rejected_creation_does_not_burn_a_number(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await world(sign_up, db_session)
        other = await create_team(w.owner, w.workspace["id"], key="DES", name="Дизайн")
        foreign_state = (await team_states(w.owner, other["id"]))["Todo"]["id"]

        bad = await w.owner.post(
            f"{API}/tasks",
            json={"title": "X", "team_id": w.team["id"], "state_id": foreign_state},
        )
        good = await w.task()

        assert bad.status_code == 400
        assert bad.json()["error"]["code"] == "invalid_state"
        assert good["key"] == "ENG-1"

    async def test_in_project_takes_its_team(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await world(sign_up, db_session)

        task = await create_task(w.owner, project_id=w.project["id"])

        assert (task["team_id"], task["project_id"]) == (w.team["id"], w.project["id"])

    async def test_project_of_other_team_is_400(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await world(sign_up, db_session)
        other = await create_team(w.owner, w.workspace["id"], key="DES", name="Дизайн")

        response = await w.owner.post(
            f"{API}/tasks",
            json={"title": "X", "team_id": other["id"], "project_id": w.project["id"]},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "project_team_mismatch"

    async def test_location_is_required(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await world(sign_up, db_session)

        response = await w.owner.post(f"{API}/tasks", json={"title": "X"})

        assert response.status_code == 422

    async def test_contractor_creates_only_in_own_project(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await world(sign_up, db_session)
        contractor, _ = await w.person(
            "contractor@example.com",
            workspace_role="guest",
            project_id=w.project["id"],
            project_role="member",
        )

        in_project = await contractor.post(
            f"{API}/tasks", json={"title": "Своя", "project_id": w.project["id"]}
        )
        in_backlog = await contractor.post(
            f"{API}/tasks", json={"title": "Чужая", "team_id": w.team["id"]}
        )

        assert in_project.status_code == 201, in_project.text
        assert in_backlog.status_code == 404
        assert in_backlog.json()["error"]["code"] == "team_not_found"

    async def test_started_state_sets_started_at(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await world(sign_up, db_session)

        started = await w.task(state_id=w.states["In Progress"]["id"])
        done = await w.task(state_id=w.states["Done"]["id"])

        assert started["started_at"] is not None and started["completed_at"] is None
        assert done["completed_at"] is not None

    async def test_title_limits(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await world(sign_up, db_session)

        for title in ["", "x" * 501, "строка\nс переводом"]:
            response = await w.owner.post(
                f"{API}/tasks", json={"title": title, "team_id": w.team["id"]}
            )
            assert response.status_code == 422, title


class TestAssignee:
    async def test_assignee_gets_notification(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await world(sign_up, db_session)
        dev, dev_id = await w.person("dev@example.com", workspace_role="member")

        task = await w.task(assignee_id=dev_id)
        inbox = await dev.get(f"{API}/me/notifications")

        assert task["assignee_id"] == dev_id
        assert [(n["type"], n["task_id"]) for n in inbox.json()["items"]] == [
            ("assigned", task["id"])
        ]

    async def test_self_assignment_is_not_notified(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await world(sign_up, db_session)
        owner_id = await user_id_of(db_session, "owner@example.com")

        await w.task(assignee_id=str(owner_id))

        assert (await w.owner.get(f"{API}/me/notifications")).json()["items"] == []

    async def test_assignee_without_access_is_400(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await world(sign_up, db_session)
        _, stranger_id = await w.person("stranger@example.com")
        _, guest_id = await w.person("guest@example.com", workspace_role="guest")

        for user_id in (stranger_id, guest_id):
            response = await w.owner.post(
                f"{API}/tasks",
                json={"title": "X", "team_id": w.team["id"], "assignee_id": user_id},
            )
            assert response.status_code == 400
            assert response.json()["error"]["code"] == "assignee_no_access"


class TestRead:
    async def test_by_key_in_any_case_and_by_id(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await world(sign_up, db_session)
        task = await w.task()

        for ref in ("ENG-1", "eng-1", task["id"]):
            response = await w.owner.get(f"{API}/tasks/{ref}")
            assert response.status_code == 200, ref
            assert response.json()["id"] == task["id"]

    async def test_unknown_key_is_404(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await world(sign_up, db_session)

        for ref in ("ENG-99", "NOPE-1", "garbage", "00000000-0000-0000-0000-000000000000"):
            response = await w.owner.get(f"{API}/tasks/{ref}")
            assert response.status_code == 404, ref
            assert response.json()["error"]["code"] == "task_not_found"

    async def test_ambiguous_key_needs_workspace(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await world(sign_up, db_session)
        await w.task()
        second = await create_workspace(w.owner, slug="second", name="Second")
        team = await create_team(w.owner, second["id"])
        other = await create_task(w.owner, team_id=team["id"])

        ambiguous = await w.owner.get(f"{API}/tasks/ENG-1")
        resolved = await w.owner.get(f"{API}/tasks/ENG-1", params={"workspace_id": second["id"]})

        assert ambiguous.status_code == 409
        assert ambiguous.json()["error"]["code"] == "task_key_ambiguous"
        assert resolved.json()["id"] == other["id"]

    async def test_expand(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await world(sign_up, db_session)
        task = await create_task(w.owner, project_id=w.project["id"])

        response = await w.owner.get(
            f"{API}/tasks/{task['key']}", params={"expand": "creator,state,project,labels"}
        )
        bad = await w.owner.get(f"{API}/tasks/{task['key']}", params={"expand": "secrets"})

        body = response.json()
        assert body["creator"]["email"] == "owner@example.com"
        assert body["state"]["name"] == "Todo"
        assert body["project"]["name"] == w.project["name"]
        assert body["labels"] == []
        assert "assignee" not in body
        assert bad.status_code == 400
        assert bad.json()["error"]["code"] == "invalid_expand"

    async def test_hidden_from_outsiders(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await world(sign_up, db_session)
        task = await w.task()
        stranger, _ = await w.person("stranger@example.com")
        guest, _ = await w.person("guest@example.com", workspace_role="guest")

        for client in (stranger, guest):
            response = await client.get(f"{API}/tasks/{task['key']}")
            assert response.status_code == 404


class TestUpdate:
    async def test_fields_and_history(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await world(sign_up, db_session)
        task = await w.task()

        response = await w.owner.patch(
            f"{API}/tasks/{task['key']}",
            json={
                "title": "Новое название",
                "description": "Подробности",
                "priority": 2,
                "due_date": "2026-10-20",
                "project_id": w.project["id"],
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["title"], body["priority"], body["due_date"]) == (
            "Новое название",
            2,
            "2026-10-20",
        )
        assert await activity_types(w.owner, task["key"]) == [
            "task_created",
            "project_changed",
            "title_changed",
            "description_changed",
            "priority_changed",
            "due_date_changed",
        ]

    async def test_state_timestamps(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await world(sign_up, db_session)
        task = await w.task()
        url = f"{API}/tasks/{task['key']}"

        started = await w.owner.patch(url, json={"state_id": w.states["In Progress"]["id"]})
        done = await w.owner.patch(url, json={"state_id": w.states["Done"]["id"]})
        reopened = await w.owner.patch(url, json={"state_id": w.states["Todo"]["id"]})

        assert started.json()["started_at"] is not None
        assert done.json()["completed_at"] is not None
        assert done.json()["started_at"] == started.json()["started_at"]
        assert reopened.json()["completed_at"] is None
        assert reopened.json()["started_at"] == started.json()["started_at"]

    async def test_state_change_payload_has_names(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await world(sign_up, db_session)
        task = await w.task()

        await w.owner.patch(
            f"{API}/tasks/{task['key']}", json={"state_id": w.states["In Progress"]["id"]}
        )
        history = (await w.owner.get(f"{API}/tasks/{task['key']}/activities")).json()["items"]

        assert history[0]["type"] == "state_changed"
        assert history[0]["payload"]["from"]["name"] == "Todo"
        assert history[0]["payload"]["to"] == {
            "id": w.states["In Progress"]["id"],
            "name": "In Progress",
            "type": "started",
        }

    async def test_no_change_no_history(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await world(sign_up, db_session)
        task = await w.task(title="Same")

        await w.owner.patch(f"{API}/tasks/{task['key']}", json={"title": "Same"})

        assert await activity_types(w.owner, task["key"]) == ["task_created"]

    async def test_null_rules(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await world(sign_up, db_session)
        owner_id = str(await user_id_of(db_session, "owner@example.com"))
        task = await w.task(assignee_id=owner_id, due_date="2026-10-20")
        url = f"{API}/tasks/{task['key']}"

        cleared = await w.owner.patch(url, json={"assignee_id": None, "due_date": None})
        null_title = await w.owner.patch(url, json={"title": None})
        estimate = await w.owner.patch(url, json={"estimate": 3})

        assert (cleared.json()["assignee_id"], cleared.json()["due_date"]) == (None, None)
        assert null_title.status_code == 422
        assert estimate.status_code == 422

    async def test_move_to_invisible_project_is_404(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await world(sign_up, db_session)
        dev, _ = await w.person(
            "dev@example.com",
            workspace_role="guest",
            project_id=w.project["id"],
            project_role="member",
        )
        hidden = await create_project(w.owner, w.team["id"], name="Скрытый")
        task = await create_task(dev, project_id=w.project["id"])

        moved = await dev.patch(f"{API}/tasks/{task['key']}", json={"project_id": hidden["id"]})
        to_backlog = await dev.patch(f"{API}/tasks/{task['key']}", json={"project_id": None})

        assert moved.status_code == 404
        assert moved.json()["error"]["code"] == "project_not_found"
        assert to_backlog.status_code == 404
        assert to_backlog.json()["error"]["code"] == "team_not_found"

    async def test_viewer_cannot_edit(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await world(sign_up, db_session)
        task = await create_task(w.owner, project_id=w.project["id"])
        viewer, _ = await w.person(
            "viewer@example.com",
            workspace_role="guest",
            project_id=w.project["id"],
            project_role="viewer",
        )

        read = await viewer.get(f"{API}/tasks/{task['key']}")
        edit = await viewer.patch(f"{API}/tasks/{task['key']}", json={"title": "Нет"})

        assert read.status_code == 200
        assert edit.status_code == 403
        assert edit.json()["error"]["code"] == "insufficient_role"


class TestDelete:
    async def test_soft_delete_and_restore(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        w = await world(sign_up, db_session)
        task = await w.task()
        member, _ = await w.person("member@example.com", workspace_role="member")
        url = f"{API}/tasks/{task['key']}"

        deleted = await member.delete(url)
        gone = await w.owner.get(url)
        member_restore = await member.post(f"{url}/restore")
        restored = await w.owner.post(f"{url}/restore")
        back = await w.owner.get(url)

        assert deleted.status_code == 204
        assert gone.status_code == 404
        assert member_restore.status_code == 403
        assert restored.status_code == 200
        assert restored.json()["deleted_at"] is None
        assert back.status_code == 200
        assert await activity_types(w.owner, task["key"]) == [
            "task_created",
            "task_deleted",
            "task_restored",
        ]

    async def test_deleted_task_cannot_be_edited(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await world(sign_up, db_session)
        task = await w.task()
        await w.owner.delete(f"{API}/tasks/{task['key']}")

        response = await w.owner.patch(f"{API}/tasks/{task['key']}", json={"title": "X"})

        assert response.status_code == 404


class TestStateDeletion:
    async def test_state_with_tasks_needs_move_to(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        w = await world(sign_up, db_session)
        task = await w.task(state_id=w.states["In Progress"]["id"])
        doomed = w.states["In Progress"]["id"]

        refused = await w.owner.delete(f"{API}/states/{doomed}")
        wrong = await w.owner.delete(f"{API}/states/{doomed}", params={"move_to": doomed})
        moved = await w.owner.delete(
            f"{API}/states/{doomed}", params={"move_to": w.states["Done"]["id"]}
        )
        after = (await w.owner.get(f"{API}/tasks/{task['key']}")).json()

        assert refused.status_code == 409
        assert refused.json()["error"]["details"] == {"task_count": 1}
        assert wrong.status_code == 400
        assert wrong.json()["error"]["code"] == "invalid_move_to"
        assert moved.status_code == 204
        assert after["state_id"] == w.states["Done"]["id"]
        assert after["completed_at"] is not None
        assert (await activity_types(w.owner, task["key"]))[-1] == "state_changed"
