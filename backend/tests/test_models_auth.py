"""Таблицы этапа 1: значения по умолчанию, ограничения и каскады.

Проверяется поведение схемы в PostgreSQL, а не объявления в Python: `CHECK` и
уникальный индекс либо работают в базе, либо не существуют.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.core.enums import InstanceRole, TokenScope
from app.modules.auth.models import ApiToken, RefreshToken
from app.modules.users.models import User


def make_user(email: str = "ivan@example.com") -> User:
    return User(email=email, password_hash="$argon2id$fake", full_name="Иван Иванов")


class TestUser:
    async def test_roundtrip_with_defaults(self, db_session: AsyncSession) -> None:
        user = make_user()
        db_session.add(user)
        await db_session.flush()

        assert user.id is not None
        assert user.role == InstanceRole.USER
        assert user.is_active is True
        assert user.created_at is not None
        assert user.last_seen_at is None

    async def test_email_is_case_insensitive_unique(self, db_session: AsyncSession) -> None:
        """CITEXT: один человек не заводит два аккаунта сменой регистра."""
        db_session.add(make_user("ivan@example.com"))
        await db_session.flush()
        db_session.add(make_user("IVAN@EXAMPLE.COM"))

        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_email_lookup_ignores_case(self, db_session: AsyncSession) -> None:
        db_session.add(make_user("Ivan@Example.COM"))
        await db_session.flush()

        found = await db_session.scalar(select(User).where(User.email == "ivan@example.com"))

        assert found is not None

    async def test_role_check_rejects_unknown_value(self, db_session: AsyncSession) -> None:
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, full_name, role) "
                    "VALUES (:id, :email, 'x', 'Имя', 'root')"
                ),
                {"id": uuid7(), "email": "root@example.com"},
            )


class TestApiToken:
    async def test_roundtrip(self, db_session: AsyncSession) -> None:
        user = make_user()
        db_session.add(user)
        await db_session.flush()

        token = ApiToken(
            user_id=user.id,
            name="claude-code",
            token_hash="a" * 64,
            prefix="tkl_7fa3b2c1",
            scope=TokenScope.READ,
        )
        db_session.add(token)
        await db_session.flush()

        assert token.id is not None
        assert token.revoked_at is None
        assert token.last_used_at is None

    async def test_scope_check_rejects_unknown_value(self, db_session: AsyncSession) -> None:
        user = make_user()
        db_session.add(user)
        await db_session.flush()

        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO api_tokens (id, user_id, name, token_hash, prefix, scope) "
                    "VALUES (:id, :user_id, 'имя', :hash, 'tkl_0000', 'admin')"
                ),
                {"id": uuid7(), "user_id": user.id, "hash": "b" * 64},
            )

    async def test_token_hash_is_unique(self, db_session: AsyncSession) -> None:
        user = make_user()
        db_session.add(user)
        await db_session.flush()
        for _ in range(2):
            db_session.add(
                ApiToken(
                    user_id=user.id,
                    name="дубль",
                    token_hash="c" * 64,
                    prefix="tkl_0000",
                    scope=TokenScope.READ,
                )
            )

        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestRefreshToken:
    async def test_cascades_with_user(self, db_session: AsyncSession) -> None:
        """ON DELETE CASCADE: удалённый пользователь не оставляет живых сессий."""
        user = make_user()
        db_session.add(user)
        await db_session.flush()
        db_session.add(
            RefreshToken(
                user_id=user.id,
                token_hash="d" * 64,
                expires_at=datetime.now(UTC) + timedelta(days=30),
                user_agent="curl/8",
                ip="127.0.0.1",
            )
        )
        await db_session.flush()

        await db_session.delete(user)
        await db_session.flush()

        remaining = await db_session.scalar(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
        assert remaining is None
