"""Скрипт `backend/scripts/create_user.py`: заведение пользователя напрямую в базе."""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InstanceRole
from app.core.security import verify_password
from app.modules.users.repository import UserRepository
from scripts.create_user import ROLE_CHOICES, NewUser, ask_new_user, create_user

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "create_user.py"


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
        feed(monkeypatch, ["  ivan@example.com ", "Иван", "3"], ["secret-pass"] * 2)

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

    def test_role_outside_the_list_is_asked_again(self, monkeypatch: pytest.MonkeyPatch) -> None:
        feed(monkeypatch, ["ivan@example.com", "Иван", "admin", "0", "9", "2"], ["secret-pass"] * 2)

        new_user = ask_new_user()

        assert new_user is not None
        assert new_user.role == InstanceRole.SUPPORT

    def test_mismatched_passwords(self, monkeypatch: pytest.MonkeyPatch) -> None:
        feed(monkeypatch, ["ivan@example.com", "Иван", ""], ["secret-pass", "other-pass"])

        assert ask_new_user() is None

    def test_roles_are_numbered_from_user_up(self) -> None:
        """Первым идёт безопасный вариант по умолчанию, дальше — по возрастанию прав."""
        assert ROLE_CHOICES == (
            InstanceRole.USER,
            InstanceRole.SUPPORT,
            InstanceRole.ADMIN,
            InstanceRole.SUPERADMIN,
        )


class TestLaunch:
    def test_reads_root_env_from_any_directory(self, tmp_path: Path) -> None:
        """Настройки ищут `.env` от текущего каталога — скрипт обязан перейти в корень сам."""
        probe = (
            f"import runpy, os; runpy.run_path({str(SCRIPT)!r}, run_name='probe')"
            "['enter_project_root'](); "
            "from app.core.config import get_settings; get_settings(); print(os.getcwd())"
        )
        env = {k: v for k, v in os.environ.items() if not k.startswith(("DB__", "SECURITY__"))}

        result = subprocess.run(
            [sys.executable, "-c", probe], cwd=tmp_path, env=env, capture_output=True, text=True
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(SCRIPT.parents[2])
