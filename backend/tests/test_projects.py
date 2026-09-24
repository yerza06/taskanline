"""Проекты: создание, архив, даты, ответственный, видимость, участники."""

from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.org import API, create_project, create_team, create_workspace, grant, user_id_of

SignUp = Callable[..., Awaitable[AsyncClient]]


async def setup(
    sign_up: SignUp, *, private: bool = False
) -> tuple[AsyncClient, dict[str, Any], dict[str, Any]]:
    owner = await sign_up("owner@example.com")
    workspace = await create_workspace(owner)
    team = await create_team(owner, workspace["id"], is_private=private)
    return owner, workspace, team


class TestCreate:
    async def test_team_member_creates_project(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        _, workspace, team = await setup(sign_up)
        member = await sign_up("anna@example.com")
        await grant(
            db_session,
            user_id=await user_id_of(db_session, "anna@example.com"),
            workspace_id=workspace["id"],
            workspace_role="member",
        )

        project = await create_project(member, team["id"])

        assert project["status"] == "planned"
        assert project["team_id"] == team["id"]
        assert project["workspace_id"] == workspace["id"]

    async def test_lead_must_be_workspace_member(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner, _, team = await setup(sign_up)
        await sign_up("stranger@example.com")
        stranger = await user_id_of(db_session, "stranger@example.com")

        response = await owner.post(
            f"{API}/teams/{team['id']}/projects", json={"name": "Сайт", "lead_id": str(stranger)}
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "lead_not_member"

    async def test_target_before_start_is_400(self, sign_up: SignUp) -> None:
        owner, _, team = await setup(sign_up)

        response = await owner.post(
            f"{API}/teams/{team['id']}/projects",
            json={"name": "Сайт", "start_date": "2026-10-01", "target_date": "2026-09-01"},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_date_range"


class TestUpdate:
    async def test_partial_date_update_is_checked_against_stored(self, sign_up: SignUp) -> None:
        """Прислали только target_date — сверять надо с сохранённым start_date."""
        owner, _, team = await setup(sign_up)
        project = await create_project(owner, team["id"], start_date="2026-10-01")

        response = await owner.patch(
            f"{API}/projects/{project['id']}", json={"target_date": "2026-09-01"}
        )

        assert response.status_code == 400

    async def test_update_fields(self, sign_up: SignUp) -> None:
        owner, _, team = await setup(sign_up)
        project = await create_project(owner, team["id"])

        response = await owner.patch(
            f"{API}/projects/{project['id']}",
            json={"name": "Новый сайт", "status": "in_progress", "description": "Описание"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Новый сайт"
        assert response.json()["status"] == "in_progress"


class TestArchive:
    async def test_archived_leaves_list_and_comes_back(self, sign_up: SignUp) -> None:
        owner, _, team = await setup(sign_up)
        project = await create_project(owner, team["id"])

        archived = await owner.post(f"{API}/projects/{project['id']}/archive")
        default_list = (await owner.get(f"{API}/teams/{team['id']}/projects")).json()["items"]
        full_list = (
            await owner.get(
                f"{API}/teams/{team['id']}/projects", params={"include_archived": "true"}
            )
        ).json()["items"]
        restored = await owner.post(f"{API}/projects/{project['id']}/unarchive")

        assert archived.status_code == 200
        assert archived.json()["archived_at"] is not None
        assert default_list == []
        assert [p["id"] for p in full_list] == [project["id"]]
        assert restored.json()["archived_at"] is None


class TestVisibility:
    async def test_project_viewer_sees_project_not_team(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner, workspace, team = await setup(sign_up)
        project = await create_project(owner, team["id"])
        viewer = await sign_up("anna@example.com")
        await grant(
            db_session,
            user_id=await user_id_of(db_session, "anna@example.com"),
            workspace_id=workspace["id"],
            workspace_role="guest",
            project_id=project["id"],
            project_role="viewer",
        )

        assert (await viewer.get(f"{API}/projects/{project['id']}")).status_code == 200
        assert (await viewer.get(f"{API}/teams/{team['id']}")).status_code == 404
        edit = await viewer.patch(f"{API}/projects/{project['id']}", json={"name": "Нет"})
        assert edit.status_code == 403

    async def test_private_team_project_is_hidden_from_member(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner, workspace, team = await setup(sign_up, private=True)
        project = await create_project(owner, team["id"])
        member = await sign_up("anna@example.com")
        await grant(
            db_session,
            user_id=await user_id_of(db_session, "anna@example.com"),
            workspace_id=workspace["id"],
            workspace_role="member",
        )

        response = await member.get(f"{API}/projects/{project['id']}")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "project_not_found"


class TestMembers:
    async def test_change_and_remove(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        owner, workspace, team = await setup(sign_up)
        project = await create_project(owner, team["id"])
        await sign_up("anna@example.com")
        anna = await user_id_of(db_session, "anna@example.com")
        await grant(
            db_session,
            user_id=anna,
            workspace_id=workspace["id"],
            workspace_role="guest",
            project_id=project["id"],
            project_role="viewer",
        )

        changed = await owner.patch(
            f"{API}/projects/{project['id']}/members/{anna}", json={"role": "member"}
        )
        removed = await owner.delete(f"{API}/projects/{project['id']}/members/{anna}")
        listed = (await owner.get(f"{API}/projects/{project['id']}/members")).json()["items"]

        assert changed.json()["role"] == "member"
        assert removed.status_code == 204
        assert listed == []
