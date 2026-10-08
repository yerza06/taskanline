"""Админ-панель: изоляция раздела, роли инстанса, подтверждение паролем, инварианты,
каскад блокировки, анонимизация, журнал аудита и отсутствие утечки содержимого.

Первый зарегистрировавшийся в тесте — `superadmin` (как и на живом инстансе).
"""

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import issue_reauth_token
from app.modules.admin.models import AdminAuditLog
from app.modules.auth.cookies import REAUTH_COOKIE
from app.modules.users.models import User
from app.openapi import dump
from tests.org import (
    API,
    RecordingMailer,
    create_project,
    create_task,
    create_team,
    create_workspace,
    user_id_of,
)

SignUp = Callable[..., Awaitable[AsyncClient]]
PASSWORD = "correct horse battery"
ZERO = "00000000-0000-0000-0000-000000000000"


async def set_role(session: AsyncSession, email: str, role: str) -> None:
    await session.execute(update(User).where(User.email == email).values(role=role))
    await session.flush()


async def reauth(client: AsyncClient) -> None:
    response = await client.post(f"{API}/admin/reauth", json={"password": PASSWORD})
    assert response.status_code == 200, response.text


async def pat(client: AsyncClient, scope: str = "read_write") -> str:
    response = await client.post(f"{API}/me/tokens", json={"name": "agent", "scope": scope})
    token: str = response.json()["token"]
    return token


async def audit_rows(session: AsyncSession) -> list[AdminAuditLog]:
    return list(
        (await session.scalars(select(AdminAuditLog).order_by(AdminAuditLog.created_at))).all()
    )


# Каждый маршрут раздела: метод, путь, тело. Пути с id — на заведомо несуществующий
# объект: проверки доступа срабатывают раньше поиска.
ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/admin/session", None),
    ("POST", "/admin/session", None),
    ("POST", "/admin/reauth", {"password": "x"}),
    ("GET", "/admin/stats", None),
    ("GET", "/admin/audit", None),
    ("GET", "/admin/users", None),
    ("GET", f"/admin/users/{ZERO}", None),
    ("POST", f"/admin/users/{ZERO}/block", None),
    ("POST", f"/admin/users/{ZERO}/unblock", None),
    ("POST", f"/admin/users/{ZERO}/reset-password", None),
    ("DELETE", f"/admin/users/{ZERO}/tokens/{ZERO}", None),
    ("PATCH", f"/admin/users/{ZERO}/role", {"role": "admin"}),
    ("DELETE", f"/admin/users/{ZERO}", None),
    ("GET", "/admin/workspaces", None),
    ("GET", f"/admin/workspaces/{ZERO}", None),
    ("DELETE", f"/admin/workspaces/{ZERO}", None),
    ("POST", f"/admin/workspaces/{ZERO}/grant-ownership", None),
    ("GET", "/admin/settings", None),
    ("PATCH", "/admin/settings", {"instance_name": "X"}),
]
READS = {(m, p) for m, p, _ in ROUTES if m == "GET"} | {
    ("POST", "/admin/session"),
    ("POST", "/admin/reauth"),
}


def test_every_admin_route_is_covered() -> None:
    documented = {
        (method.upper(), path.removeprefix("/api/v1"))
        for path, item in json.loads(dump())["paths"].items()
        if path.startswith("/api/v1/admin")
        for method in item
    }
    listed = {
        (m, p.replace(ZERO, "{user_id}" if "/users/" in p else "{workspace_id}"))
        for m, p, _ in ROUTES
    }
    listed = {(m, p.replace("/tokens/{user_id}", "/tokens/{token_id}")) for m, p in listed}
    assert documented == listed


class TestIsolation:
    async def test_user_gets_404_everywhere(self, sign_up: SignUp) -> None:
        await sign_up("root@example.com")
        person = await sign_up("person@example.com")

        for method, path, body in ROUTES:
            response = await person.request(method, f"{API}{path}", json=body)
            assert response.status_code == 404, (method, path)
            assert response.json()["error"]["code"] == "not_found"

    async def test_pat_gets_session_required_everywhere(self, sign_up: SignUp) -> None:
        root = await sign_up("root@example.com")
        token = await pat(root)

        for method, path, body in ROUTES:
            response = await root.request(
                method, f"{API}{path}", json=body, headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 403, (method, path)
            assert response.json()["error"]["code"] == "session_required"

    async def test_anonymous_gets_401(self, client: AsyncClient) -> None:
        for method, path, body in ROUTES:
            response = await client.request(method, f"{API}{path}", json=body)
            assert response.status_code == 401, (method, path)


class TestRoleMatrix:
    async def test_support_reads_but_never_writes(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        await sign_up("root@example.com")
        support = await sign_up("support@example.com")
        await set_role(db_session, "support@example.com", "support")

        for method, path, body in ROUTES:
            response = await support.request(method, f"{API}{path}", json=body)
            if (method, path) in READS:
                assert response.status_code in (200, 403, 404), (method, path)
                assert response.json().get("error", {}).get("code") != "insufficient_role"
            else:
                assert response.status_code == 403, (method, path)
                assert response.json()["error"]["code"] == "insufficient_role", (method, path)

    async def test_admin_manages_people_but_not_roles_or_settings(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        await sign_up("root@example.com")
        admin = await sign_up("admin@example.com")
        await set_role(db_session, "admin@example.com", "admin")
        await sign_up("person@example.com")
        person_id = await user_id_of(db_session, "person@example.com")
        await reauth(admin)

        blocked = await admin.post(f"{API}/admin/users/{person_id}/block")
        role = await admin.patch(f"{API}/admin/users/{person_id}/role", json={"role": "admin"})
        settings = await admin.patch(f"{API}/admin/settings", json={"instance_name": "X"})
        delete = await admin.delete(f"{API}/admin/users/{person_id}")

        assert blocked.status_code == 200
        for response in (role, settings, delete):
            assert response.status_code == 403
            assert response.json()["error"] == {
                "code": "insufficient_role",
                "message": "Недостаточно прав для этого действия",
                "details": {"required": "superadmin"},
            }

    async def test_admin_cannot_touch_superadmin(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        await sign_up("root@example.com")
        admin = await sign_up("admin@example.com")
        await set_role(db_session, "admin@example.com", "admin")
        root_id = await user_id_of(db_session, "root@example.com")

        response = await admin.post(f"{API}/admin/users/{root_id}/block")

        assert response.status_code == 403
        assert response.json()["error"]["details"] == {"required": "superadmin"}


class TestReauth:
    async def test_dangerous_action_needs_fresh_password(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        root = await sign_up("root@example.com")

        before = await root.patch(f"{API}/admin/settings", json={"instance_name": "Acme"})
        session = await root.post(f"{API}/admin/reauth", json={"password": PASSWORD})
        after = await root.patch(f"{API}/admin/settings", json={"instance_name": "Acme"})

        assert before.status_code == 403
        assert before.json()["error"]["code"] == "reauth_required"
        until = datetime.fromisoformat(session.json()["reauth_until"])
        assert timedelta(minutes=14) < until - datetime.now(UTC) <= timedelta(minutes=15)
        assert after.status_code == 200
        assert after.json()["instance_name"] == "Acme"

    async def test_expired_or_foreign_confirmation_is_refused(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        root = await sign_up("root@example.com")
        root_id = await user_id_of(db_session, "root@example.com")
        stale, _ = issue_reauth_token(root_id, now=datetime.now(UTC) - timedelta(minutes=16))
        foreign, _ = issue_reauth_token(UUID(int=1))

        for token in (stale, foreign):
            root.cookies.set(REAUTH_COOKIE, token, path="/api/v1/admin")
            response = await root.patch(f"{API}/admin/settings", json={"instance_name": "X"})
            assert response.json()["error"]["code"] == "reauth_required"

    async def test_three_wrong_passwords_end_the_session(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        root = await sign_up("root@example.com")

        first = await root.post(f"{API}/admin/reauth", json={"password": "nope"})
        second = await root.post(f"{API}/admin/reauth", json={"password": "nope"})
        third = await root.post(f"{API}/admin/reauth", json={"password": "nope"})
        refreshed = await root.post(f"{API}/auth/refresh")

        assert (first.status_code, first.json()["error"]["details"]) == (403, {"attempts_left": 2})
        assert second.json()["error"]["details"] == {"attempts_left": 1}
        assert third.status_code == 401
        assert third.json()["error"]["code"] == "session_terminated"
        assert refreshed.status_code == 401
        actions = [row.action for row in await audit_rows(db_session)]
        assert actions == ["reauth_failed"] * 3


class TestInvariants:
    async def test_last_superadmin_stays(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        root = await sign_up("root@example.com")
        root_id = await user_id_of(db_session, "root@example.com")
        await reauth(root)

        for response in (
            await root.post(f"{API}/admin/users/{root_id}/block"),
            await root.patch(f"{API}/admin/users/{root_id}/role", json={"role": "admin"}),
            await root.delete(f"{API}/admin/users/{root_id}"),
        ):
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "last_superadmin"

        await sign_up("second@example.com")
        await set_role(db_session, "second@example.com", "superadmin")
        demoted = await root.patch(f"{API}/admin/users/{root_id}/role", json={"role": "admin"})

        assert demoted.status_code == 200
        # Неудачные попытки не оставили следов в журнале — только успешная смена роли.
        assert [row.action for row in await audit_rows(db_session)] == ["user_role_changed"]

    async def test_block_kills_session_and_tokens_at_once(
        self, sign_up: SignUp, db_session: AsyncSession, new_client: Callable[[], AsyncClient]
    ) -> None:
        root = await sign_up("root@example.com")
        victim = await sign_up("victim@example.com")
        token = await pat(victim)
        victim_id = await user_id_of(db_session, "victim@example.com")

        await root.post(f"{API}/admin/users/{victim_id}/block")

        assert (await victim.get(f"{API}/me")).status_code == 401
        assert (await victim.post(f"{API}/auth/refresh")).status_code == 401
        agent = new_client()
        assert (
            await agent.get(f"{API}/me", headers={"Authorization": f"Bearer {token}"})
        ).status_code == 401
        login = await new_client().post(
            f"{API}/auth/login", json={"email": "victim@example.com", "password": PASSWORD}
        )
        assert login.status_code == 401

        await root.post(f"{API}/admin/users/{victim_id}/unblock")
        again = await new_client().post(
            f"{API}/auth/login", json={"email": "victim@example.com", "password": PASSWORD}
        )
        assert again.status_code == 200
        # Токены, отозванные блокировкой, не воскресают.
        assert (
            await agent.get(f"{API}/me", headers={"Authorization": f"Bearer {token}"})
        ).status_code == 401

    async def test_last_owner_cannot_be_deleted(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        root = await sign_up("root@example.com")
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner, slug="solo", name="Solo")
        owner_id = await user_id_of(db_session, "owner@example.com")
        await reauth(root)

        refused = await root.delete(f"{API}/admin/users/{owner_id}")

        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "last_owner_of_workspace"
        assert refused.json()["error"]["details"]["workspaces"] == [
            {"id": workspace["id"], "name": "Solo", "slug": "solo"}
        ]

    async def test_deletion_anonymizes_and_keeps_history(
        self, sign_up: SignUp, db_session: AsyncSession, new_client: Callable[[], AsyncClient]
    ) -> None:
        root = await sign_up("root@example.com")
        owner = await sign_up("owner@example.com")
        dev = await sign_up("dev@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        dev_id = await user_id_of(db_session, "dev@example.com")
        from tests.org import grant

        await grant(
            db_session, user_id=dev_id, workspace_id=workspace["id"], workspace_role="member",
            team_id=team["id"], team_role="member",
        )  # fmt: skip
        task = await create_task(dev, team_id=team["id"], title="Работа разработчика")
        await dev.post(f"{API}/tasks/{task['id']}/comments", json={"body": "Сделано"})
        await reauth(root)

        deleted = await root.delete(f"{API}/admin/users/{dev_id}")
        kept = await owner.get(f"{API}/tasks/{task['id']}?expand=creator")
        comments = await owner.get(f"{API}/tasks/{task['id']}/comments")
        login = await new_client().post(
            f"{API}/auth/login", json={"email": "dev@example.com", "password": PASSWORD}
        )
        listed = await root.get(f"{API}/admin/users", params={"status": "deleted"})

        assert deleted.status_code == 204
        assert kept.json()["creator"]["full_name"] == "Удалённый пользователь"
        assert kept.json()["creator"]["email"].endswith("@deleted.invalid")
        assert comments.json()["items"][0]["author_id"] == str(dev_id)
        assert login.status_code == 401
        assert [row["id"] for row in listed.json()["items"]] == [str(dev_id)]


class TestAudit:
    async def test_each_action_writes_one_entry_with_actor_and_ip(
        self, sign_up: SignUp, db_session: AsyncSession, mailer: RecordingMailer
    ) -> None:
        root = await sign_up("root@example.com")
        person = await sign_up("person@example.com")
        token_id = (await person.post(f"{API}/me/tokens", json={"name": "a"})).json()["id"]
        workspace = await create_workspace(person, slug="doomed")
        person_id = await user_id_of(db_session, "person@example.com")
        root_id = await user_id_of(db_session, "root@example.com")
        await reauth(root)

        await root.post(f"{API}/admin/session")
        await root.post(f"{API}/admin/users/{person_id}/reset-password")
        await root.delete(f"{API}/admin/users/{person_id}/tokens/{token_id}")
        await root.post(f"{API}/admin/users/{person_id}/block")
        await root.post(f"{API}/admin/users/{person_id}/unblock")
        await root.patch(f"{API}/admin/users/{person_id}/role", json={"role": "support"})
        await root.post(f"{API}/admin/workspaces/{workspace['id']}/grant-ownership")
        await root.patch(f"{API}/admin/settings", json={"registration_mode": "invite_only"})
        await root.delete(f"{API}/admin/workspaces/{workspace['id']}")

        rows = await audit_rows(db_session)
        assert [row.action for row in rows] == [
            "admin_login",
            "password_reset_sent",
            "token_revoked",
            "user_blocked",
            "user_unblocked",
            "user_role_changed",
            "workspace_ownership_granted",
            "settings_changed",
            "workspace_deleted",
        ]
        assert {row.actor_id for row in rows} == {root_id}
        assert all(row.ip is not None for row in rows)
        assert rows[5].payload == {"from": "user", "to": "support", "email": "person@example.com"}
        assert rows[7].payload == {"registration_mode": {"from": "open", "to": "invite_only"}}
        page = await root.get(f"{API}/admin/audit", params={"target_id": str(person_id)})
        assert page.json()["items"][0]["action"] == "user_role_changed"
        assert page.json()["items"][0]["actor"]["email"] == "root@example.com"
        assert len(mailer.sent) == 1

    async def test_filters_and_pages(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        root = await sign_up("root@example.com")
        for _ in range(3):
            await root.post(f"{API}/admin/session")
        await sign_up("x@example.com")
        x_id = await user_id_of(db_session, "x@example.com")
        await root.post(f"{API}/admin/users/{x_id}/block")

        first = await root.get(f"{API}/admin/audit", params={"limit": 2})
        second = await root.get(
            f"{API}/admin/audit", params={"limit": 2, "cursor": first.json()["next_cursor"]}
        )
        logins = await root.get(f"{API}/admin/audit", params={"action": "admin_login"})

        assert [e["action"] for e in first.json()["items"]] == ["user_blocked", "admin_login"]
        assert len(second.json()["items"]) == 2 and not second.json()["has_more"]
        assert len(logins.json()["items"]) == 3


class TestScenarioE:
    """Сценарий Е: блокировка гасит доступ, регистрация закрывается, всё — в журнале."""

    async def test_block_and_close_registration(
        self, sign_up: SignUp, db_session: AsyncSession, new_client: Callable[[], AsyncClient]
    ) -> None:
        root = await sign_up("root@example.com")
        leaver = await sign_up("leaver@example.com")
        agent_token = await pat(leaver)
        leaver_id = await user_id_of(db_session, "leaver@example.com")
        await root.post(f"{API}/admin/session")

        await root.post(f"{API}/admin/users/{leaver_id}/block")
        await reauth(root)
        closed = await root.patch(
            f"{API}/admin/settings", json={"registration_mode": "invite_only"}
        )
        register = await new_client().post(
            f"{API}/auth/register",
            json={"email": "new@example.com", "password": PASSWORD, "full_name": "Новый"},
        )
        audit = await root.get(f"{API}/admin/audit")

        assert (await leaver.get(f"{API}/me")).status_code == 401
        assert (
            await new_client().get(f"{API}/me", headers={"Authorization": f"Bearer {agent_token}"})
        ).status_code == 401
        assert closed.json()["registration_mode"] == "invite_only"
        assert register.status_code == 403
        assert register.json()["error"]["code"] == "registration_closed"
        entries = {e["action"]: e for e in audit.json()["items"]}
        assert entries["user_blocked"]["actor"]["email"] == "root@example.com"
        assert entries["user_blocked"]["ip"] is not None
        assert entries["settings_changed"]["payload"] == {
            "registration_mode": {"from": "open", "to": "invite_only"}
        }


class TestContent:
    async def test_no_task_content_in_any_admin_response(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        root = await sign_up("root@example.com")
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        await create_project(owner, team["id"], name="Проект", description="SECRET-DESCRIPTION")
        task = await create_task(
            owner, team_id=team["id"], title="SECRET-TITLE", description="SECRET-BODY"
        )
        await owner.post(f"{API}/tasks/{task['id']}/comments", json={"body": "SECRET-COMMENT"})
        owner_id = await user_id_of(db_session, "owner@example.com")

        for path in (
            "/admin/stats",
            "/admin/users",
            f"/admin/users/{owner_id}",
            "/admin/workspaces",
            f"/admin/workspaces/{workspace['id']}",
            "/admin/audit",
            "/admin/settings",
        ):
            response = await root.get(f"{API}{path}")
            assert response.status_code == 200, path
            assert "SECRET" not in response.text, path


class TestReading:
    async def test_users_search_and_detail(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        root = await sign_up("root@example.com", "Корень")
        await sign_up("anna@example.com", "Анна Иванова")
        await sign_up("boris@example.com", "Борис")
        anna_id = await user_id_of(db_session, "anna@example.com")

        found = await root.get(f"{API}/admin/users", params={"q": "иванова"})
        admins = await root.get(f"{API}/admin/users", params={"role": "superadmin"})
        page = await root.get(f"{API}/admin/users", params={"limit": 2})
        detail = await root.get(f"{API}/admin/users/{anna_id}")

        assert [u["email"] for u in found.json()["items"]] == ["anna@example.com"]
        assert [u["email"] for u in admins.json()["items"]] == ["root@example.com"]
        assert page.json()["has_more"] is True
        body = detail.json()
        assert body["status"] == "active"
        assert [login["kind"] for login in body["logins"]] == ["registration"]
        assert body["memberships"] == [] and body["tokens"] == []

    async def test_workspaces_with_counts_and_sorting(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        root = await sign_up("root@example.com")
        owner = await sign_up("owner@example.com")
        big = await create_workspace(owner, slug="big", name="Big")
        await create_workspace(owner, slug="small", name="Small")
        team = await create_team(owner, big["id"])
        for n in range(3):
            await create_task(owner, team_id=team["id"], title=f"t{n}")

        by_tasks = await root.get(f"{API}/admin/workspaces", params={"sort": "tasks"})
        paged = await root.get(f"{API}/admin/workspaces", params={"sort": "tasks", "limit": 1})
        rest = await root.get(
            f"{API}/admin/workspaces",
            params={"sort": "tasks", "limit": 1, "cursor": paged.json()["next_cursor"]},
        )
        detail = await root.get(f"{API}/admin/workspaces/{big['id']}")

        rows = by_tasks.json()["items"]
        assert [(r["slug"], r["tasks"], r["teams"], r["members"]) for r in rows] == [
            ("big", 3, 1, 1),
            ("small", 0, 0, 1),
        ]
        assert rows[0]["owners"][0]["email"] == "owner@example.com"
        assert rows[0]["last_activity_at"] is not None
        assert [r["slug"] for r in rest.json()["items"]] == ["small"]
        assert detail.json()["member_list"][0]["role"] == "owner"

    async def test_stats(self, sign_up: SignUp, db_session: AsyncSession) -> None:
        root = await sign_up("root@example.com")
        await create_workspace(root)

        stats = (await root.get(f"{API}/admin/stats")).json()

        assert stats["users"] == {"total": 1, "active": 1, "blocked": 0, "deleted": 0}
        assert stats["workspaces"] == 1
        assert stats["migration"] == stats["migration_head"] == "0006_admin"


class TestOwnershipAndReset:
    async def test_grant_ownership_notifies_owners(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        root = await sign_up("root@example.com")
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await reauth(root)

        granted = await root.post(f"{API}/admin/workspaces/{workspace['id']}/grant-ownership")
        inbox = await owner.get(f"{API}/me/notifications")
        inside = await root.get(f"{API}/workspaces/{workspace['id']}")

        roles = {m["email"]: m["role"] for m in granted.json()["member_list"]}
        assert roles == {"owner@example.com": "owner", "root@example.com": "owner"}
        assert [n["type"] for n in inbox.json()["items"]] == ["ownership_granted"]
        assert inside.status_code == 200

    async def test_password_reset_by_link(
        self,
        sign_up: SignUp,
        db_session: AsyncSession,
        mailer: RecordingMailer,
        new_client: Callable[[], AsyncClient],
    ) -> None:
        import re

        root = await sign_up("root@example.com")
        person = await sign_up("person@example.com")
        person_id = await user_id_of(db_session, "person@example.com")

        await root.post(f"{API}/admin/users/{person_id}/reset-password")
        (message,) = mailer.sent
        token = re.search(r"/reset-password/(\w+)", message.body)
        assert token is not None and message.to == "person@example.com"
        reset = await new_client().post(
            f"{API}/auth/reset-password",
            json={"token": token.group(1), "password": "brand new password"},
        )
        reused = await new_client().post(
            f"{API}/auth/reset-password",
            json={"token": token.group(1), "password": "another password"},
        )
        login = await new_client().post(
            f"{API}/auth/login",
            json={"email": "person@example.com", "password": "brand new password"},
        )

        assert reset.status_code == 200
        assert (await person.get(f"{API}/me")).status_code in (200, 401)
        assert (await person.post(f"{API}/auth/refresh")).status_code == 401
        assert reused.json()["error"]["code"] == "reset_token_invalid"
        assert login.status_code == 200

    async def test_forgot_password_does_not_reveal_accounts(
        self, sign_up: SignUp, mailer: RecordingMailer, new_client: Callable[[], AsyncClient]
    ) -> None:
        await sign_up("person@example.com")

        known = await new_client().post(
            f"{API}/auth/forgot-password", json={"email": "person@example.com"}
        )
        unknown = await new_client().post(
            f"{API}/auth/forgot-password", json={"email": "ghost@example.com"}
        )

        assert known.status_code == unknown.status_code == 204
        assert [m.to for m in mailer.sent] == ["person@example.com"]


@pytest.mark.parametrize("domains", [["ACME.com", "@acme.com"], ["mail.acme.io"]])
async def test_settings_normalizes_domains(
    sign_up: SignUp, db_session: AsyncSession, domains: list[str]
) -> None:
    root = await sign_up("root@example.com")
    await reauth(root)

    response = await root.patch(f"{API}/admin/settings", json={"allowed_email_domains": domains})

    assert response.status_code == 200
    assert response.json()["allowed_email_domains"] == sorted(
        {d.lower().lstrip("@") for d in domains}
    )
