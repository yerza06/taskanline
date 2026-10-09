"""Скрипт `backend/scripts/create_user.py`: заведение пользователя напрямую в базе."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InstanceRole
from app.core.security import verify_password
from app.modules.users.repository import UserRepository
from scripts.create_user import build_parser, create_user


class TestCreateUser:
    async def test_creates_user_with_hashed_password(self, db_session: AsyncSession) -> None:
        code = await create_user(
            db_session,
            email="Ivan@Example.COM",
            full_name="Иван",
            password="correct-horse",
            role=InstanceRole.USER,
        )

        user = await UserRepository(db_session).get_by_email("ivan@example.com")
        assert code == 0
        assert user is not None
        assert user.email == "ivan@example.com"
        assert user.full_name == "Иван"
        assert user.role == InstanceRole.USER
        assert user.password_hash != "correct-horse"
        assert verify_password(user.password_hash, "correct-horse")

    async def test_sets_requested_role(self, db_session: AsyncSession) -> None:
        code = await create_user(
            db_session,
            email="admin@example.com",
            full_name="Админ",
            password="correct-horse",
            role=InstanceRole.SUPERADMIN,
        )

        user = await UserRepository(db_session).get_by_email("admin@example.com")
        assert code == 0
        assert user is not None
        assert user.role == InstanceRole.SUPERADMIN

    async def test_existing_email_returns_error_code(self, db_session: AsyncSession) -> None:
        kwargs = {"full_name": "Иван", "password": "correct-horse", "role": InstanceRole.USER}
        await create_user(db_session, email="ivan@example.com", **kwargs)  # type: ignore[arg-type]

        code = await create_user(db_session, email="IVAN@example.com", **kwargs)  # type: ignore[arg-type]

        assert code == 1

    @pytest.mark.parametrize(
        ("email", "password", "full_name"),
        [
            ("not-an-email", "correct-horse", "Иван"),
            ("ivan@example.com", "short", "Иван"),
            ("ivan@example.com", "correct-horse", ""),
        ],
    )
    async def test_invalid_input_returns_error_code(
        self, db_session: AsyncSession, email: str, password: str, full_name: str
    ) -> None:
        """Правила те же, что у регистрации через API."""
        code = await create_user(
            db_session, email=email, full_name=full_name, password=password, role=InstanceRole.USER
        )

        assert code == 1
        assert await UserRepository(db_session).get_by_email(email.lower()) is None


class TestParser:
    def test_role_defaults_to_user(self) -> None:
        args = build_parser().parse_args(["--email", "ivan@example.com", "--full-name", "Иван"])

        assert args.role == InstanceRole.USER
        assert args.password is None

    def test_rejects_unknown_role(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--email", "a@b.c", "--full-name", "А", "--role", "root"])

    def test_requires_email(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--full-name", "Иван"])
