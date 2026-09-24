"""Приглашения: создание, письмо, дубли, список, отзыв и отзыв вместе с объектом."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail import MailMessage
from app.core.security import hash_token
from app.modules.invitations.models import Invitation
from tests.org import (
    API,
    RecordingMailer,
    create_project,
    create_team,
    create_workspace,
    grant,
    invite_token,
    user_id_of,
)

SignUp = Callable[..., Awaitable[AsyncClient]]
NewClient = Callable[[], AsyncClient]


async def read_only_client(owner: AsyncClient, new_client: NewClient) -> AsyncClient:
    """Клиент агента с PAT `scope=read`: своей cookie-сессии у него нет."""
    response = await owner.post(f"{API}/me/tokens", json={"name": "agent", "scope": "read"})
    assert response.status_code == 201, response.text
    agent = new_client()
    agent.headers["Authorization"] = f"Bearer {response.json()['token']}"
    return agent


async def invite(
    client: AsyncClient,
    scope_type: str,
    scope_id: str,
    *,
    email: str = "anna@example.com",
    role: str = "member",
) -> Response:
    return await client.post(
        f"{API}/invitations",
        json={"email": email, "scope_type": scope_type, "scope_id": scope_id, "role": role},
    )


async def statuses(db_session: AsyncSession) -> dict[str, str]:
    db_session.expunge_all()
    rows = (await db_session.execute(select(Invitation.email, Invitation.status))).all()
    return {email: status for email, status in rows}  # noqa: C416


class TestCreate:
    async def test_invitation_is_mailed(self, sign_up: SignUp, mailer: RecordingMailer) -> None:
        owner = await sign_up("owner@example.com", "Ольга Владелец")
        workspace = await create_workspace(owner, name="Acme")

        response = await invite(owner, "workspace", workspace["id"], email="Anna@Example.com")

        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "anna@example.com"
        assert body["status"] == "pending"
        assert "token" not in body
        [message] = mailer.sent
        assert message.to == "anna@example.com"
        assert "Ольга Владелец" in message.body
        assert "Acme" in message.body
        assert f"/invite/{invite_token(mailer)}" in message.body

    async def test_only_hash_is_stored(
        self, sign_up: SignUp, mailer: RecordingMailer, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await invite(owner, "workspace", workspace["id"])

        stored = await db_session.scalar(select(Invitation))

        assert stored is not None
        assert stored.token_hash == hash_token(invite_token(mailer))

    async def test_role_must_exist_on_level(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)

        lead = await invite(owner, "workspace", workspace["id"], role="lead")
        owner_role = await invite(owner, "workspace", workspace["id"], role="owner")

        assert lead.status_code == 422
        assert owner_role.status_code == 422

    async def test_duplicate_pending_is_409(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await invite(owner, "workspace", workspace["id"])

        again = await invite(owner, "workspace", workspace["id"], email="ANNA@example.com")

        assert again.status_code == 409
        assert again.json()["error"]["code"] == "invitation_exists"

    async def test_expired_pending_does_not_block(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        first = (await invite(owner, "workspace", workspace["id"])).json()
        await db_session.execute(
            update(Invitation)
            .where(Invitation.id == first["id"])
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )

        again = await invite(owner, "workspace", workspace["id"])

        assert again.status_code == 201
        db_session.expunge_all()
        old = await db_session.get(Invitation, first["id"])
        assert old is not None
        assert old.status == "expired"

    async def test_existing_member_is_409(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await sign_up("anna@example.com")
        await grant(
            db_session,
            user_id=await user_id_of(db_session, "anna@example.com"),
            workspace_id=workspace["id"],
            workspace_role="member",
        )

        response = await invite(owner, "workspace", workspace["id"])

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "already_member"

    async def test_workspace_member_can_be_invited_deeper(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        project = await create_project(owner, team["id"])
        await sign_up("anna@example.com")
        await grant(
            db_session,
            user_id=await user_id_of(db_session, "anna@example.com"),
            workspace_id=workspace["id"],
            workspace_role="member",
        )

        response = await invite(owner, "project", project["id"], role="admin")

        assert response.status_code == 201

    async def test_mail_failure_does_not_fail_request(self, app: FastAPI, sign_up: SignUp) -> None:
        """Письмо уходит после ответа: сбой SMTP не отменяет приглашения."""

        class Broken:
            async def send(self, message: MailMessage) -> None:
                raise ConnectionError("smtp down")

        app.state.mailer = Broken()
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)

        response = await invite(owner, "workspace", workspace["id"])

        assert response.status_code == 201

    async def test_team_member_cannot_invite_to_team(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        member = await sign_up("bob@example.com")
        await grant(
            db_session,
            user_id=await user_id_of(db_session, "bob@example.com"),
            workspace_id=workspace["id"],
            workspace_role="member",
        )

        response = await invite(member, "team", team["id"])

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    async def test_read_scope_cannot_create(self, sign_up: SignUp, new_client: NewClient) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        agent = await read_only_client(owner, new_client)

        response = await invite(agent, "workspace", workspace["id"])

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_scope"


class TestList:
    async def test_lists_pending_only(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await invite(owner, "workspace", workspace["id"], email="anna@example.com")
        bob = (await invite(owner, "workspace", workspace["id"], email="bob@example.com")).json()
        carl = (await invite(owner, "workspace", workspace["id"], email="carl@example.com")).json()
        await owner.delete(f"{API}/invitations/{bob['id']}")
        await db_session.execute(
            update(Invitation)
            .where(Invitation.id == carl["id"])
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )

        items = (
            await owner.get(f"{API}/invitations", params={"workspace_id": workspace["id"]})
        ).json()["items"]

        assert [item["email"] for item in items] == ["anna@example.com"]

    async def test_member_cannot_list(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        member = await sign_up("bob@example.com")
        await grant(
            db_session,
            user_id=await user_id_of(db_session, "bob@example.com"),
            workspace_id=workspace["id"],
            workspace_role="member",
        )

        response = await member.get(f"{API}/invitations", params={"workspace_id": workspace["id"]})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"


class TestRevoke:
    async def test_revoke_once(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        invitation = (await invite(owner, "workspace", workspace["id"])).json()

        first = await owner.delete(f"{API}/invitations/{invitation['id']}")
        second = await owner.delete(f"{API}/invitations/{invitation['id']}")

        assert first.status_code == 204
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "invitation_not_pending"
        assert second.json()["error"]["details"] == {"status": "revoked"}

    async def test_stranger_gets_404(self, sign_up: SignUp) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        invitation = (await invite(owner, "workspace", workspace["id"])).json()
        stranger = await sign_up("stranger@example.com")

        response = await stranger.delete(f"{API}/invitations/{invitation['id']}")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "invitation_not_found"

    async def test_member_cannot_revoke(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        """Объект виден (workspace), но роли не хватает — 403, а не 404."""
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        invitation = (await invite(owner, "workspace", workspace["id"])).json()
        member = await sign_up("bob@example.com")
        await grant(
            db_session,
            user_id=await user_id_of(db_session, "bob@example.com"),
            workspace_id=workspace["id"],
            workspace_role="member",
        )

        response = await member.delete(f"{API}/invitations/{invitation['id']}")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_role"

    async def test_read_scope_cannot_revoke(self, sign_up: SignUp, new_client: NewClient) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        invitation = (await invite(owner, "workspace", workspace["id"])).json()
        agent = await read_only_client(owner, new_client)

        response = await agent.delete(f"{API}/invitations/{invitation['id']}")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_scope"

    async def test_deleting_team_revokes_invitations_inside(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        project = await create_project(owner, team["id"])
        await invite(owner, "team", team["id"], email="anna@example.com")
        await invite(owner, "project", project["id"], email="bob@example.com")
        await invite(owner, "workspace", workspace["id"], email="carl@example.com")

        await owner.delete(f"{API}/teams/{team['id']}")

        assert await statuses(db_session) == {
            "anna@example.com": "revoked",
            "bob@example.com": "revoked",
            "carl@example.com": "pending",
        }

    async def test_deleting_project_revokes_its_invitations(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        project = await create_project(owner, team["id"])
        await invite(owner, "project", project["id"])

        await owner.delete(f"{API}/projects/{project['id']}")

        assert await statuses(db_session) == {"anna@example.com": "revoked"}
