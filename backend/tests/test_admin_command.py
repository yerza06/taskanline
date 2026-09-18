"""Аварийная команда назначения роли инстанса.

Нужна ровно на один случай: единственный superadmin потерян, а поднять себе роль
через API невозможно по определению.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import build_parser, grant
from app.core.enums import InstanceRole
from app.modules.users.models import User


async def make_user(session: AsyncSession, email: str = "ivan@example.com") -> User:
    user = User(email=email, password_hash="$argon2id$fake", full_name="Иван")
    session.add(user)
    await session.flush()
    return user


class TestGrant:
    async def test_sets_role(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session)

        code = await grant(db_session, email="ivan@example.com", role=InstanceRole.SUPERADMIN)

        await db_session.refresh(user)
        assert code == 0
        assert user.role == InstanceRole.SUPERADMIN

    async def test_email_is_case_insensitive(self, db_session: AsyncSession) -> None:
        user = await make_user(db_session, "Ivan@Example.COM")

        code = await grant(db_session, email="IVAN@EXAMPLE.COM", role=InstanceRole.ADMIN)

        await db_session.refresh(user)
        assert code == 0
        assert user.role == InstanceRole.ADMIN

    async def test_unknown_email_returns_error_code(self, db_session: AsyncSession) -> None:
        code = await grant(db_session, email="nobody@example.com", role=InstanceRole.ADMIN)

        assert code == 1

    async def test_demotion_is_allowed(self, db_session: AsyncSession) -> None:
        """Команда — аварийный инструмент: понижение тоже её работа."""
        user = await make_user(db_session)
        user.role = InstanceRole.SUPERADMIN
        await db_session.flush()

        code = await grant(db_session, email="ivan@example.com", role=InstanceRole.USER)

        await db_session.refresh(user)
        assert code == 0
        assert user.role == InstanceRole.USER


class TestParser:
    def test_parses_grant(self) -> None:
        args = build_parser().parse_args(
            ["grant", "--email", "ivan@example.com", "--role", "superadmin"]
        )

        assert args.email == "ivan@example.com"
        assert args.role == InstanceRole.SUPERADMIN

    def test_rejects_unknown_role(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["grant", "--email", "a@b.c", "--role", "root"])

    def test_requires_email(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["grant", "--role", "admin"])
