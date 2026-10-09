"""Заведение пользователя напрямую в базе, без регистрации через API.

    cd backend
    uv run python -m scripts.create_user --email ivan@example.com --full-name "Иван Петров"
    uv run python -m scripts.create_user --email root@example.com --full-name Root --role superadmin

Пароль спрашивается в терминале дважды и в историю shell не попадает. Флаг
`--password` есть для автоматизации, но значение в нём видно в `ps` и в истории.

Скрипт не смотрит на политику регистрации инстанса и не выдаёт сессию: доступ к
нему равносилен доступу к серверу, как у `app.admin`. Проверки адреса, длины
пароля и имени — те же, что у `POST /auth/register`.
"""

import argparse
import asyncio
import getpass
import sys

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_engine, get_sessionmaker
from app.core.enums import InstanceRole
from app.core.security import hash_password
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import RegisterRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.create_user", description="Добавить пользователя в базу"
    )
    parser.add_argument("--email", required=True, help="Адрес нового пользователя")
    parser.add_argument("--full-name", required=True, help="Имя, как его увидят коллеги")
    parser.add_argument(
        "--role",
        type=InstanceRole,
        choices=list(InstanceRole),
        default=InstanceRole.USER,
        help="Роль инстанса: superadmin | admin | support | user (по умолчанию user)",
    )
    parser.add_argument(
        "--password", help="Пароль; без флага спрашивается в терминале — так безопаснее"
    )
    return parser


async def create_user(
    session: AsyncSession, *, email: str, full_name: str, password: str, role: InstanceRole
) -> int:
    """Код возврата: 0 — пользователь создан, 1 — данные неверны или адрес занят."""
    try:
        data = RegisterRequest(email=email, password=password, full_name=full_name)
    except ValidationError as error:
        for problem in error.errors():
            field = ".".join(str(part) for part in problem["loc"])
            print(f"{field}: {problem['msg']}", file=sys.stderr)
        return 1

    users = UserRepository(session)
    if await users.get_by_email(data.email) is not None:
        print(f"Пользователь {data.email} уже существует", file=sys.stderr)
        return 1

    user = await users.create(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=role,
    )
    print(f"Создан {user.email} ({role}), id {user.id}")
    return 0


def ask_password() -> str | None:
    """Пароль с повтором; None — если ввод не совпал."""
    password = getpass.getpass("Пароль: ")
    if getpass.getpass("Ещё раз: ") != password:
        print("Пароли не совпадают", file=sys.stderr)
        return None
    return password


async def _run(args: argparse.Namespace, password: str) -> int:
    async with get_sessionmaker()() as session:
        code = await create_user(
            session, email=args.email, full_name=args.full_name, password=password, role=args.role
        )
        if code == 0:
            await session.commit()
    await get_engine().dispose()
    return code


def main() -> None:
    """Точка входа. Отделена от `create_user`, чтобы тест не поднимал настоящую сессию."""
    args = build_parser().parse_args()
    password = args.password if args.password is not None else ask_password()
    if password is None:
        raise SystemExit(1)
    raise SystemExit(asyncio.run(_run(args, password)))


if __name__ == "__main__":
    main()
