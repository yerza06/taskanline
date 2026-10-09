"""Политика инстанса: строка настроек, режим регистрации, режим обслуживания."""

from collections.abc import Awaitable, Callable
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.instance.models import InstanceSettings
from tests.org import API

SignUp = Callable[..., Awaitable[AsyncClient]]
NewClient = Callable[[], AsyncClient]


def account(email: str) -> dict[str, str]:
    return {"email": email, "password": "correct horse battery", "full_name": "Человек"}


async def set_policy(session: AsyncSession, **values: Any) -> None:
    await session.execute(update(InstanceSettings).values(**values))
    await session.flush()


async def test_migration_creates_closed_instance(db_session: AsyncSession) -> None:
    # Фикстура открыла регистрацию; значение по умолчанию смотрим у самой колонки.
    default = await db_session.scalar(
        text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'instance_settings' AND column_name = 'registration_mode'"
        )
    )
    row = (await db_session.execute(text("SELECT * FROM instance_settings"))).mappings().one()

    assert "invite_only" in str(default)
    assert (
        row["id"],
        row["instance_name"],
        row["invitation_ttl_days"],
        row["maintenance_mode"],
    ) == (
        1,
        "TasKanLine",
        7,
        False,
    )


async def test_public_instance_info(client: AsyncClient, db_session: AsyncSession) -> None:
    await set_policy(db_session, instance_name="Acme Tracker", registration_mode="invite_only")

    response = await client.get(f"{API}/instance")

    assert response.status_code == 200
    assert response.json() == {"instance_name": "Acme Tracker", "registration_mode": "invite_only"}


class TestRegistrationMode:
    async def test_first_user_registers_even_when_closed(
        self, new_client: NewClient, db_session: AsyncSession
    ) -> None:
        await set_policy(db_session, registration_mode="invite_only")

        first = await new_client().post(f"{API}/auth/register", json=account("first@example.com"))
        second = await new_client().post(f"{API}/auth/register", json=account("second@example.com"))

        assert first.status_code == 201
        assert first.json()["user"]["role"] == "superadmin"
        assert second.status_code == 403
        assert second.json()["error"]["code"] == "registration_closed"

    async def test_domain_allowlist(
        self, sign_up: SignUp, new_client: NewClient, db_session: AsyncSession
    ) -> None:
        await sign_up("owner@example.com")
        await set_policy(
            db_session, registration_mode="domain_allowlist", allowed_email_domains=["acme.com"]
        )

        allowed = await new_client().post(f"{API}/auth/register", json=account("dev@ACME.com"))
        refused = await new_client().post(f"{API}/auth/register", json=account("x@evil.com"))
        sub = await new_client().post(f"{API}/auth/register", json=account("x@mail.acme.com"))

        assert allowed.status_code == 201
        assert refused.status_code == 403
        assert refused.json()["error"]["code"] == "registration_closed"
        assert sub.status_code == 403

    async def test_open(
        self, sign_up: SignUp, new_client: NewClient, db_session: AsyncSession
    ) -> None:
        await sign_up("owner@example.com")
        await set_policy(db_session, registration_mode="open")

        response = await new_client().post(f"{API}/auth/register", json=account("any@example.com"))

        assert response.status_code == 201


class TestMaintenance:
    async def test_only_instance_roles_get_through(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        admin = await sign_up("admin@example.com")  # первый — superadmin
        person = await sign_up("person@example.com")
        await set_policy(db_session, maintenance_mode=True)

        blocked = await person.get(f"{API}/me")
        allowed = await admin.get(f"{API}/me")

        assert blocked.status_code == 503
        assert blocked.json()["error"]["code"] == "maintenance"
        assert allowed.status_code == 200


async def test_invitation_ttl_comes_from_settings(
    sign_up: SignUp, db_session: AsyncSession
) -> None:
    from datetime import UTC, datetime, timedelta

    from tests.org import create_workspace

    owner = await sign_up("owner@example.com")
    workspace = await create_workspace(owner)
    await set_policy(db_session, invitation_ttl_days=2)

    response = await owner.post(
        f"{API}/invitations",
        json={
            "email": "guest@example.com",
            "scope_type": "workspace",
            "scope_id": workspace["id"],
            "role": "member",
        },
    )

    expires = datetime.fromisoformat(response.json()["expires_at"])
    assert abs(expires - (datetime.now(UTC) + timedelta(days=2))) < timedelta(minutes=1)
