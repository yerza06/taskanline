"""Workflow-статусы команды: стандартный набор, CRUD и единственный статус по умолчанию."""

from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.org import API, create_project, create_team, create_workspace, grant, user_id_of

SignUp = Callable[..., Awaitable[AsyncClient]]


async def team_states(client: AsyncClient, team_id: str) -> list[dict[str, Any]]:
    response = await client.get(f"{API}/teams/{team_id}/states")
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def setup(sign_up: SignUp) -> tuple[AsyncClient, dict[str, Any]]:
    owner = await sign_up("owner@example.com")
    workspace = await create_workspace(owner)
    team = await create_team(owner, workspace["id"])
    return owner, team


class TestDefaults:
    async def test_new_team_gets_standard_states(self, sign_up: SignUp) -> None:
        owner, team = await setup(sign_up)

        states = await team_states(owner, team["id"])

        assert [(s["name"], s["type"], s["is_default"]) for s in states] == [
            ("Backlog", "backlog", False),
            ("Todo", "unstarted", True),
            ("In Progress", "started", False),
            ("Done", "completed", False),
            ("Canceled", "canceled", False),
        ]
        assert [s["position"] for s in states] == [0, 1, 2, 3, 4]


class TestCreate:
    async def test_appends_to_the_end(self, sign_up: SignUp) -> None:
        owner, team = await setup(sign_up)

        response = await owner.post(
            f"{API}/teams/{team['id']}/states",
            json={"name": "На ревью", "type": "started", "color": "#AABBCC"},
        )

        assert response.status_code == 201, response.text
        assert response.json()["position"] == 5
        assert response.json()["is_default"] is False

    async def test_name_is_unique_case_insensitive(self, sign_up: SignUp) -> None:
        owner, team = await setup(sign_up)

        response = await owner.post(
            f"{API}/teams/{team['id']}/states",
            json={"name": "todo", "type": "unstarted", "color": "#000000"},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "state_name_taken"

    async def test_new_default_takes_the_flag(self, sign_up: SignUp) -> None:
        owner, team = await setup(sign_up)

        response = await owner.post(
            f"{API}/teams/{team['id']}/states",
            json={"name": "Входящие", "type": "backlog", "color": "#000000", "is_default": True},
        )

        assert response.status_code == 201, response.text
        defaults = [s["name"] for s in await team_states(owner, team["id"]) if s["is_default"]]
        assert defaults == ["Входящие"]

    async def test_bad_color_is_422(self, sign_up: SignUp) -> None:
        owner, team = await setup(sign_up)

        response = await owner.post(
            f"{API}/teams/{team['id']}/states",
            json={"name": "X", "type": "started", "color": "red"},
        )

        assert response.status_code == 422


class TestUpdate:
    async def test_rename_and_recolor(self, sign_up: SignUp) -> None:
        owner, team = await setup(sign_up)
        todo = (await team_states(owner, team["id"]))[1]

        response = await owner.patch(
            f"{API}/states/{todo['id']}", json={"name": "К работе", "color": "#111111"}
        )

        assert response.status_code == 200, response.text
        assert (response.json()["name"], response.json()["color"]) == ("К работе", "#111111")

    async def test_rename_to_taken_name_is_409(self, sign_up: SignUp) -> None:
        owner, team = await setup(sign_up)
        todo = (await team_states(owner, team["id"]))[1]

        response = await owner.patch(f"{API}/states/{todo['id']}", json={"name": "DONE"})

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "state_name_taken"

    async def test_default_moves_with_flag(self, sign_up: SignUp) -> None:
        owner, team = await setup(sign_up)
        backlog = (await team_states(owner, team["id"]))[0]

        response = await owner.patch(f"{API}/states/{backlog['id']}", json={"is_default": True})

        assert response.status_code == 200, response.text
        defaults = [s["name"] for s in await team_states(owner, team["id"]) if s["is_default"]]
        assert defaults == ["Backlog"]

    async def test_cannot_unset_default_directly(self, sign_up: SignUp) -> None:
        owner, team = await setup(sign_up)
        todo = (await team_states(owner, team["id"]))[1]

        response = await owner.patch(f"{API}/states/{todo['id']}", json={"is_default": False})

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "state_is_default"

    async def test_type_is_fixed(self, sign_up: SignUp) -> None:
        """Тип не меняется: на нём держатся started_at/completed_at уже лежащих задач."""
        owner, team = await setup(sign_up)
        todo = (await team_states(owner, team["id"]))[1]

        response = await owner.patch(f"{API}/states/{todo['id']}", json={"type": "started"})

        assert response.status_code == 422


class TestDelete:
    async def test_empty_state_is_deleted(self, sign_up: SignUp) -> None:
        owner, team = await setup(sign_up)
        canceled = (await team_states(owner, team["id"]))[4]

        response = await owner.delete(f"{API}/states/{canceled['id']}")

        assert response.status_code == 204
        assert len(await team_states(owner, team["id"])) == 4

    async def test_default_state_cannot_be_deleted(self, sign_up: SignUp) -> None:
        owner, team = await setup(sign_up)
        todo = (await team_states(owner, team["id"]))[1]

        response = await owner.delete(f"{API}/states/{todo['id']}")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "state_is_default"


class TestVisibility:
    async def test_project_contractor_reads_team_states(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        """Подрядчику без членства в команде статусы нужны, чтобы двигать свои задачи."""
        owner, team = await setup(sign_up)
        project = await create_project(owner, team["id"])
        contractor = await sign_up("contractor@example.com")
        await grant(
            db_session,
            user_id=await user_id_of(db_session, "contractor@example.com"),
            workspace_id=team["workspace_id"],
            workspace_role="guest",
            project_id=project["id"],
            project_role="member",
        )

        assert len(await team_states(contractor, team["id"])) == 5
        team_response = await contractor.get(f"{API}/teams/{team['id']}")
        assert team_response.status_code == 404

    async def test_stranger_gets_404(self, sign_up: SignUp) -> None:
        _, team = await setup(sign_up)
        stranger = await sign_up("stranger@example.com")

        response = await stranger.get(f"{API}/teams/{team['id']}/states")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "team_not_found"
