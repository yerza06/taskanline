"""Скрипт `backend/scripts/create_user.py`: заведение пользователя напрямую в базе."""

from collections.abc import Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InstanceRole
from app.core.security import verify_password
from app.modules.users.repository import UserRepository
from scripts.create_user import NewUser, ask_new_user, create_user


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


def feed(monkeypatch: pytest.MonkeyPatch, answers: list[str], passwords: list[str]) -> None:
    """Подменяет терминал: input() и getpass() отдают ответы по очереди."""
    answer_iter: Iterator[str] = iter(answers)
    password_iter: Iterator[str] = iter(passwords)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answer_iter))
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": next(password_iter))


class TestAskNewUser:
    def test_collects_answers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        feed(monkeypatch, ["  ivan@example.com ", "Иван", "admin"], ["secret-pass"] * 2)

        assert ask_new_user() == NewUser(
            email="ivan@example.com",
            full_name="Иван",
            password="secret-pass",
            role=InstanceRole.ADMIN,
        )

    def test_empty_role_means_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        feed(monkeypatch, ["ivan@example.com", "Иван", ""], ["secret-pass"] * 2)

        new_user = ask_new_user()

        assert new_user is not None
        assert new_user.role == InstanceRole.USER

    def test_unknown_role_is_asked_again(self, monkeypatch: pytest.MonkeyPatch) -> None:
        feed(monkeypatch, ["ivan@example.com", "Иван", "root", "Support"], ["secret-pass"] * 2)

        new_user = ask_new_user()

        assert new_user is not None
        assert new_user.role == InstanceRole.SUPPORT

    def test_mismatched_passwords(self, monkeypatch: pytest.MonkeyPatch) -> None:
        feed(monkeypatch, ["ivan@example.com", "Иван", ""], ["secret-pass", "other-pass"])

        assert ask_new_user() is None
