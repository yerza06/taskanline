"""Команды: ключ, приватность, изменение, удаление, участники."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.org import API, create_team, create_workspace, grant, user_id_of

SignUp = Callable[..., Awaitable[AsyncClient]]


async def join(
    sign_up: SignUp,
    db_session: AsyncSession,
    email: str,
    workspace_id: str,
    workspace_role: str,
    team_id: str | None = None,
    team_role: str | None = None,
) -> AsyncClient:
    client = await sign_up(email)
    await grant(
        db_session,
        user_id=await user_id_of(db_session, email),
        workspace_id=workspace_id,
        workspace_role=workspace_role,
        team_id=team_id,
        team_role=team_role,
    )
    return client


class TestCreate:
    async def test_key_is_uppercased_and_creator_leads(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)

        team = await create_team(owner, workspace["id"], key="eng")

        assert team["key"] == "ENG"
        members = (await owner.get(f"{API}/teams/{team['id']}/members")).json()["items"]
        assert [(m["email"], m["role"]) for m in members] == [("owner@example.com", "lead")]

    @pytest.mark.parametrize("key", ["E", "ENGINE", "EN1", "ЕНГ"])
    async def test_invalid_key_is_422(self, sign_up: SignUp, key: str) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)

        response = await owner.post(
            f"{API}/workspaces/{workspace['id']}/teams", json={"key": key, "name": "X"}
        )

        assert response.status_code == 422

    async def test_newline_in_name_is_422(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)

        response = await owner.post(
            f"{API}/workspaces/{workspace['id']}/teams",
            json={"key": "ENG", "name": "Acme\nX"},
        )

        assert response.status_code == 422

    async def test_duplicate_key_is_409(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await create_team(owner, workspace["id"], key="ENG")

        response = await owner.post(
            f"{API}/workspaces/{workspace['id']}/teams", json={"key": "eng", "name": "Второй"}
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "team_key_taken"

    async def test_same_key_in_another_workspace(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")
        first = await create_workspace(owner, slug="first")
        second = await create_workspace(owner, slug="second")
        await create_team(owner, first["id"], key="ENG")

        await create_team(owner, second["id"], key="ENG")


class TestPrivacy:
    async def test_member_does_not_see_private_team(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await create_team(owner, workspace["id"], key="ENG")
        secret = await create_team(owner, workspace["id"], key="SEC", is_private=True)
        member = await join(sign_up, db_session, "anna@example.com", workspace["id"], "member")

        listed = (await member.get(f"{API}/workspaces/{workspace['id']}/teams")).json()["items"]
        direct = await member.get(f"{API}/teams/{secret['id']}")

        assert [team["key"] for team in listed] == ["ENG"]
        assert direct.status_code == 404

    async def test_admin_sees_private_team(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await create_team(owner, workspace["id"], key="SEC", is_private=True)
        admin = await join(sign_up, db_session, "anna@example.com", workspace["id"], "admin")

        listed = (await admin.get(f"{API}/workspaces/{workspace['id']}/teams")).json()["items"]

        assert [team["key"] for team in listed] == ["SEC"]

    async def test_private_team_member_sees_it(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        secret = await create_team(owner, workspace["id"], key="SEC", is_private=True)
        member = await join(
            sign_up,
            db_session,
            "anna@example.com",
            workspace["id"],
            "member",
            secret["id"],
            "member",
        )

        assert (await member.get(f"{API}/teams/{secret['id']}")).status_code == 200

    async def test_guest_sees_only_own_teams(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await create_team(owner, workspace["id"], key="ENG")
        ops = await create_team(owner, workspace["id"], key="OPS")
        guest = await join(
            sign_up, db_session, "anna@example.com", workspace["id"], "guest", ops["id"], "member"
        )

        listed = (await guest.get(f"{API}/workspaces/{workspace['id']}/teams")).json()["items"]

        assert [team["key"] for team in listed] == ["OPS"]


class TestUpdateDelete:
    async def test_admin_renames(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        admin = await join(sign_up, db_session, "anna@example.com", workspace["id"], "admin")

        response = await admin.patch(f"{API}/teams/{team['id']}", json={"name": "Разработка"})

        assert response.status_code == 200
        assert response.json()["name"] == "Разработка"

    async def test_key_change_needs_owner(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        """Ключ входит в идентификаторы всех задач — менять его может только владелец."""
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        admin = await join(sign_up, db_session, "anna@example.com", workspace["id"], "admin")

        by_admin = await admin.patch(f"{API}/teams/{team['id']}", json={"key": "DEV"})
        by_owner = await owner.patch(f"{API}/teams/{team['id']}", json={"key": "dev"})

        assert by_admin.status_code == 403
        assert by_owner.status_code == 200
        assert by_owner.json()["key"] == "DEV"

    async def test_key_change_to_taken_is_409(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await create_team(owner, workspace["id"], key="OPS")
        team = await create_team(owner, workspace["id"], key="ENG")

        response = await owner.patch(f"{API}/teams/{team['id']}", json={"key": "OPS"})

        assert response.status_code == 409

    async def test_delete(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])

        assert (await owner.delete(f"{API}/teams/{team['id']}")).status_code == 204
        assert (await owner.get(f"{API}/teams/{team['id']}")).status_code == 404


class TestMembers:
    async def test_lead_promotes_member(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        await join(
            sign_up, db_session, "anna@example.com", workspace["id"], "guest", team["id"], "member"
        )
        anna = await user_id_of(db_session, "anna@example.com")

        response = await owner.patch(
            f"{API}/teams/{team['id']}/members/{anna}", json={"role": "lead"}
        )

        assert response.status_code == 200
        assert response.json()["role"] == "lead"

    async def test_remove_member(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        await join(
            sign_up, db_session, "anna@example.com", workspace["id"], "member", team["id"], "member"
        )
        anna = await user_id_of(db_session, "anna@example.com")

        response = await owner.delete(f"{API}/teams/{team['id']}/members/{anna}")

        assert response.status_code == 204
        emails = [
            m["email"]
            for m in (await owner.get(f"{API}/teams/{team['id']}/members")).json()["items"]
        ]
        assert "anna@example.com" not in emails

    async def test_non_member_is_404(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        await join(sign_up, db_session, "anna@example.com", workspace["id"], "member")
        anna = await user_id_of(db_session, "anna@example.com")

        response = await owner.delete(f"{API}/teams/{team['id']}/members/{anna}")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "member_not_found"
