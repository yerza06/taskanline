"""Рабочие пространства: создание, видимость, изменение, участники, владение."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.teams.models import Team, TeamMember
from tests.org import API, create_workspace, grant, user_id_of

SignUp = Callable[..., Awaitable[AsyncClient]]


def code(response: object) -> str:
    return response.json()["error"]["code"]  # type: ignore[attr-defined, no-any-return]


class TestCreate:
    async def test_creator_becomes_owner(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")

        workspace = await create_workspace(owner, slug="Acme")

        assert workspace["slug"] == "acme"
        members = (await owner.get(f"{API}/workspaces/{workspace['id']}/members")).json()["items"]
        assert [(m["email"], m["role"]) for m in members] == [("owner@example.com", "owner")]

    async def test_taken_slug_is_409(self, sign_up: SignUp) -> None:
        await create_workspace(await sign_up("owner@example.com"), slug="acme")
        other = await sign_up("other@example.com")

        response = await other.post(f"{API}/workspaces", json={"name": "X", "slug": "ACME"})

        assert response.status_code == 409
        assert code(response) == "workspace_slug_taken"

    @pytest.mark.parametrize("slug", ["a", "acme corp", "x" * 41, "акме"])
    async def test_invalid_slug_is_422(self, sign_up: SignUp, slug: str) -> None:
        owner = await sign_up("owner@example.com")

        response = await owner.post(f"{API}/workspaces", json={"name": "Acme", "slug": slug})

        assert response.status_code == 422

    async def test_read_token_cannot_create(
        self, sign_up: SignUp, new_client: Callable[[], AsyncClient]
    ) -> None:
        owner = await sign_up("owner@example.com")
        created = await owner.post(f"{API}/me/tokens", json={"name": "agent", "scope": "read"})
        agent = new_client()

        response = await agent.post(
            f"{API}/workspaces",
            json={"name": "Acme", "slug": "acme"},
            headers={"Authorization": f"Bearer {created.json()['token']}"},
        )

        assert response.status_code == 403
        assert code(response) == "insufficient_scope"


class TestVisibility:
    async def test_list_shows_only_mine(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")
        other = await sign_up("other@example.com")
        await create_workspace(owner, slug="mine")
        await create_workspace(other, slug="theirs")

        items = (await owner.get(f"{API}/workspaces")).json()["items"]

        assert [item["slug"] for item in items] == ["mine"]

    async def test_stranger_gets_404(self, sign_up: SignUp) -> None:
        workspace = await create_workspace(await sign_up("owner@example.com"))
        stranger = await sign_up("stranger@example.com")

        response = await stranger.get(f"{API}/workspaces/{workspace['id']}")

        assert response.status_code == 404
        assert code(response) == "workspace_not_found"

    async def test_instance_superadmin_is_a_stranger(self, sign_up: SignUp) -> None:
        """Роль инстанса не открывает чужую работу: тихого доступа нет."""
        root = await sign_up("root@example.com")  # первый зарегистрированный — superadmin
        workspace = await create_workspace(await sign_up("owner@example.com"))

        response = await root.get(f"{API}/workspaces/{workspace['id']}")

        assert response.status_code == 404

    async def test_malformed_id_is_404(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")

        response = await owner.get(f"{API}/workspaces/not-a-uuid")

        assert response.status_code == 404
        assert code(response) == "workspace_not_found"


class TestUpdateDelete:
    async def test_update_name_and_slug(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)

        response = await owner.patch(
            f"{API}/workspaces/{workspace['id']}", json={"name": "Acme Corp", "slug": "Acme-Corp"}
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Acme Corp"
        assert response.json()["slug"] == "acme-corp"

    async def test_update_to_taken_slug_is_409(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")
        await create_workspace(owner, slug="taken")
        workspace = await create_workspace(owner, slug="mine")

        response = await owner.patch(f"{API}/workspaces/{workspace['id']}", json={"slug": "taken"})

        assert response.status_code == 409

    async def test_null_name_is_422(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)

        response = await owner.patch(f"{API}/workspaces/{workspace['id']}", json={"name": None})

        assert response.status_code == 422

    async def test_deleted_workspace_is_gone(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)

        deleted = await owner.delete(f"{API}/workspaces/{workspace['id']}")

        assert deleted.status_code == 204
        assert (await owner.get(f"{API}/workspaces/{workspace['id']}")).status_code == 404


class TestMembers:
    async def _join(
        self, sign_up: SignUp, db_session: AsyncSession, workspace_id: str, email: str, role: str
    ) -> AsyncClient:
        client = await sign_up(email)
        await grant(
            db_session,
            user_id=await user_id_of(db_session, email),
            workspace_id=workspace_id,
            workspace_role=role,
        )
        return client

    async def test_admin_changes_member_role(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        workspace = await create_workspace(await sign_up("owner@example.com"))
        admin = await self._join(sign_up, db_session, workspace["id"], "admin@example.com", "admin")
        await self._join(sign_up, db_session, workspace["id"], "bob@example.com", "member")
        bob = await user_id_of(db_session, "bob@example.com")

        response = await admin.patch(
            f"{API}/workspaces/{workspace['id']}/members/{bob}", json={"role": "guest"}
        )

        assert response.status_code == 200
        assert response.json()["role"] == "guest"

    async def test_admin_cannot_grant_owner(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        workspace = await create_workspace(await sign_up("owner@example.com"))
        admin = await self._join(sign_up, db_session, workspace["id"], "admin@example.com", "admin")
        await self._join(sign_up, db_session, workspace["id"], "bob@example.com", "member")
        bob = await user_id_of(db_session, "bob@example.com")

        response = await admin.patch(
            f"{API}/workspaces/{workspace['id']}/members/{bob}", json={"role": "owner"}
        )

        assert response.status_code == 403
        assert code(response) == "insufficient_role"

    async def test_admin_cannot_remove_owner(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        workspace = await create_workspace(await sign_up("owner@example.com"))
        admin = await self._join(sign_up, db_session, workspace["id"], "admin@example.com", "admin")
        owner_id = await user_id_of(db_session, "owner@example.com")

        response = await admin.delete(f"{API}/workspaces/{workspace['id']}/members/{owner_id}")

        assert response.status_code == 403

    async def test_last_owner_cannot_step_down(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        owner_id = await user_id_of(db_session, "owner@example.com")

        demoted = await owner.patch(
            f"{API}/workspaces/{workspace['id']}/members/{owner_id}", json={"role": "admin"}
        )
        left = await owner.delete(f"{API}/workspaces/{workspace['id']}/members/{owner_id}")

        assert demoted.status_code == 409
        assert code(demoted) == "last_owner"
        assert left.status_code == 409

    async def test_one_of_two_owners_can_step_down(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        second = await self._join(sign_up, db_session, workspace["id"], "anna@example.com", "owner")
        anna = await user_id_of(db_session, "anna@example.com")
        owner_id = await user_id_of(db_session, "owner@example.com")

        first = await owner.patch(
            f"{API}/workspaces/{workspace['id']}/members/{anna}", json={"role": "admin"}
        )
        # Анна больше не владелец — и снять последнего владельца уже не может.
        back = await second.patch(
            f"{API}/workspaces/{workspace['id']}/members/{owner_id}", json={"role": "admin"}
        )

        assert first.status_code == 200
        assert back.status_code == 403

    async def test_unknown_member_is_404(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        stranger = await sign_up("stranger@example.com")
        stranger_id = await user_id_of(db_session, "stranger@example.com")
        assert stranger is not None

        response = await owner.delete(f"{API}/workspaces/{workspace['id']}/members/{stranger_id}")

        assert response.status_code == 404
        assert code(response) == "member_not_found"

    async def test_removal_drops_team_membership(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = Team(workspace_id=workspace["id"], key="ENG", name="Eng")
        db_session.add(team)
        await db_session.flush()
        await sign_up("anna@example.com")
        anna = await user_id_of(db_session, "anna@example.com")
        await grant(
            db_session,
            user_id=anna,
            workspace_id=workspace["id"],
            workspace_role="member",
            team_id=team.id,
            team_role="lead",
        )

        response = await owner.delete(f"{API}/workspaces/{workspace['id']}/members/{anna}")

        assert response.status_code == 204
        db_session.expunge_all()
        assert await db_session.scalar(select(TeamMember).where(TeamMember.user_id == anna)) is None


class TestTransfer:
    async def test_transfer_swaps_roles(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await sign_up("anna@example.com")
        anna = await user_id_of(db_session, "anna@example.com")
        await grant(db_session, user_id=anna, workspace_id=workspace["id"], workspace_role="member")

        response = await owner.post(
            f"{API}/workspaces/{workspace['id']}/transfer-ownership", json={"user_id": str(anna)}
        )

        assert response.status_code == 204
        roles = {
            m["email"]: m["role"]
            for m in (await owner.get(f"{API}/workspaces/{workspace['id']}/members")).json()[
                "items"
            ]
        }
        assert roles == {"owner@example.com": "admin", "anna@example.com": "owner"}

    async def test_transfer_to_non_member_is_404(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await sign_up("stranger@example.com")
        stranger = await user_id_of(db_session, "stranger@example.com")

        response = await owner.post(
            f"{API}/workspaces/{workspace['id']}/transfer-ownership",
            json={"user_id": str(stranger)},
        )

        assert response.status_code == 404

    async def test_transfer_to_self_is_400(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        owner_id = await user_id_of(db_session, "owner@example.com")

        response = await owner.post(
            f"{API}/workspaces/{workspace['id']}/transfer-ownership",
            json={"user_id": str(owner_id)},
        )

        assert response.status_code == 400
        assert code(response) == "invalid_transfer"
