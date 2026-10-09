"""Превью приглашения по токену и его принятие — с сессией и без."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.invitations.models import Invitation
from tests.org import (
    API,
    PASSWORD,
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


async def invited(
    sign_up: SignUp,
    mailer: RecordingMailer,
    *,
    email: str = "anna@example.com",
    scope: str = "workspace",
    role: str = "member",
) -> tuple[AsyncClient, dict[str, Any], str]:
    """Владелец, его пространство и токен приглашения на выбранный уровень."""
    owner = await sign_up("owner@example.com", "Ольга Владелец")
    workspace = await create_workspace(owner, name="Acme")
    scope_id = workspace["id"]
    if scope != "workspace":
        team = await create_team(owner, workspace["id"])
        scope_id = (
            team["id"] if scope == "team" else (await create_project(owner, team["id"]))["id"]
        )
    response = await owner.post(
        f"{API}/invitations",
        json={"email": email, "scope_type": scope, "scope_id": scope_id, "role": role},
    )
    assert response.status_code == 201, response.text
    return owner, {**workspace, "scope_id": scope_id}, invite_token(mailer)


async def expire_all(db_session: AsyncSession) -> None:
    await db_session.execute(
        update(Invitation).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )


class TestPreview:
    async def test_shows_only_safe_fields(
        self, sign_up: SignUp, mailer: RecordingMailer, new_client: NewClient
    ) -> None:
        _, _, token = await invited(sign_up, mailer)

        response = await new_client().get(f"{API}/invitations/token/{token}")

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {
            "workspace_name",
            "inviter_name",
            "email",
            "scope_type",
            "role",
            "status",
            "expires_at",
        }
        assert body["workspace_name"] == "Acme"
        assert body["inviter_name"] == "Ольга Владелец"
        assert body["status"] == "pending"

    async def test_unknown_token_is_404(self, new_client: NewClient) -> None:
        response = await new_client().get(f"{API}/invitations/token/nope")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "invitation_not_found"

    async def test_expiry_is_reported_and_saved(
        self,
        sign_up: SignUp,
        mailer: RecordingMailer,
        new_client: NewClient,
        db_session: AsyncSession,
    ) -> None:
        _, _, token = await invited(sign_up, mailer)
        await expire_all(db_session)

        response = await new_client().get(f"{API}/invitations/token/{token}")

        assert response.json()["status"] == "expired"


class TestAcceptWithoutSession:
    async def test_registers_and_joins(
        self, sign_up: SignUp, mailer: RecordingMailer, new_client: NewClient
    ) -> None:
        _, workspace, token = await invited(sign_up, mailer)
        anna = new_client()

        response = await anna.post(
            f"{API}/invitations/token/{token}/accept",
            json={"full_name": "Анна", "password": PASSWORD},
        )

        assert response.status_code == 200
        assert response.json()["workspace_id"] == workspace["id"]
        me = (await anna.get(f"{API}/me")).json()
        assert me["email"] == "anna@example.com"
        assert me["memberships"]["workspaces"] == [
            {"workspace_id": workspace["id"], "role": "member"}
        ]

    async def test_without_body_is_400(
        self, sign_up: SignUp, mailer: RecordingMailer, new_client: NewClient
    ) -> None:
        _, _, token = await invited(sign_up, mailer)

        response = await new_client().post(f"{API}/invitations/token/{token}/accept")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "registration_required"

    async def test_existing_account_must_log_in(
        self, sign_up: SignUp, mailer: RecordingMailer, new_client: NewClient
    ) -> None:
        _, _, token = await invited(sign_up, mailer)
        await sign_up("anna@example.com")

        response = await new_client().post(
            f"{API}/invitations/token/{token}/accept",
            json={"full_name": "Анна", "password": PASSWORD},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "login_required"

    async def test_short_password_is_422(
        self, sign_up: SignUp, mailer: RecordingMailer, new_client: NewClient
    ) -> None:
        _, _, token = await invited(sign_up, mailer)

        response = await new_client().post(
            f"{API}/invitations/token/{token}/accept",
            json={"full_name": "Анна", "password": "short"},
        )

        assert response.status_code == 422


class TestAcceptWithSession:
    async def test_matching_email_joins(self, sign_up: SignUp, mailer: RecordingMailer) -> None:
        _, workspace, token = await invited(sign_up, mailer)
        anna = await sign_up("anna@example.com")

        response = await anna.post(f"{API}/invitations/token/{token}/accept")

        assert response.status_code == 200
        workspaces = (await anna.get(f"{API}/me")).json()["memberships"]["workspaces"]
        assert workspaces == [{"workspace_id": workspace["id"], "role": "member"}]

    async def test_other_email_is_403(self, sign_up: SignUp, mailer: RecordingMailer) -> None:
        """Пересланное письмо не даёт доступа постороннему."""
        _, _, token = await invited(sign_up, mailer)
        bob = await sign_up("bob@example.com")

        response = await bob.post(f"{API}/invitations/token/{token}/accept")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "invitation_email_mismatch"

    async def test_read_token_is_403(
        self, sign_up: SignUp, mailer: RecordingMailer, new_client: NewClient
    ) -> None:
        _, _, token = await invited(sign_up, mailer)
        anna = await sign_up("anna@example.com")
        pat = (await anna.post(f"{API}/me/tokens", json={"name": "a", "scope": "read"})).json()

        response = await new_client().post(
            f"{API}/invitations/token/{token}/accept",
            headers={"Authorization": f"Bearer {pat['token']}"},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "insufficient_scope"

    async def test_second_accept_is_409(self, sign_up: SignUp, mailer: RecordingMailer) -> None:
        _, _, token = await invited(sign_up, mailer)
        anna = await sign_up("anna@example.com")
        await anna.post(f"{API}/invitations/token/{token}/accept")

        again = await anna.post(f"{API}/invitations/token/{token}/accept")

        assert again.status_code == 409
        assert again.json()["error"]["details"] == {"status": "accepted"}

    async def test_expired_is_409(
        self, sign_up: SignUp, mailer: RecordingMailer, db_session: AsyncSession
    ) -> None:
        _, _, token = await invited(sign_up, mailer)
        anna = await sign_up("anna@example.com")
        await expire_all(db_session)

        response = await anna.post(f"{API}/invitations/token/{token}/accept")

        assert response.status_code == 409
        assert response.json()["error"]["details"] == {"status": "expired"}

    async def test_revoked_is_409(self, sign_up: SignUp, mailer: RecordingMailer) -> None:
        owner, workspace, token = await invited(sign_up, mailer)
        listed = await owner.get(f"{API}/invitations", params={"workspace_id": workspace["id"]})
        await owner.delete(f"{API}/invitations/{listed.json()['items'][0]['id']}")
        anna = await sign_up("anna@example.com")

        response = await anna.post(f"{API}/invitations/token/{token}/accept")

        assert response.status_code == 409


class TestGrant:
    async def test_team_invitation_adds_guest_and_team_member(
        self, sign_up: SignUp, mailer: RecordingMailer
    ) -> None:
        _, workspace, token = await invited(sign_up, mailer, scope="team", role="lead")
        anna = await sign_up("anna@example.com")

        await anna.post(f"{API}/invitations/token/{token}/accept")

        memberships = (await anna.get(f"{API}/me")).json()["memberships"]
        assert memberships["workspaces"] == [{"workspace_id": workspace["id"], "role": "guest"}]
        assert memberships["teams"] == [
            {"team_id": workspace["scope_id"], "workspace_id": workspace["id"], "role": "lead"}
        ]

    async def test_accept_never_lowers_workspace_role(
        self, sign_up: SignUp, mailer: RecordingMailer, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        project = await create_project(owner, team["id"])
        anna = await sign_up("anna@example.com")
        await grant(
            db_session,
            user_id=await user_id_of(db_session, "anna@example.com"),
            workspace_id=workspace["id"],
            workspace_role="admin",
        )
        await owner.post(
            f"{API}/invitations",
            json={
                "email": "anna@example.com",
                "scope_type": "project",
                "scope_id": project["id"],
                "role": "viewer",
            },
        )

        await anna.post(f"{API}/invitations/token/{invite_token(mailer)}/accept")

        memberships = (await anna.get(f"{API}/me")).json()["memberships"]
        assert memberships["workspaces"][0]["role"] == "admin"
        assert memberships["projects"][0]["role"] == "viewer"
