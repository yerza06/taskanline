"""Заведение пользователя напрямую в базе, без регистрации через API.

    make create-user
    # или: cd backend && uv run python -m scripts.create_user

Скрипт по очереди спрашивает адрес, имя, роль инстанса и пароль. Пароль вводится
через getpass дважды: на экран и в историю shell он не попадает.

Скрипт не смотрит на политику регистрации инстанса и не выдаёт сессию: доступ к
нему равносилен доступу к серверу, как у `app.admin`. Проверки адреса, длины
пароля и имени — те же, что у `POST /auth/register`.
"""

import asyncio
import getpass
import sys
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_engine, get_sessionmaker
from app.core.enums import InstanceRole
from app.core.security import hash_password
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import RegisterRequest

_ROLES = " | ".join(InstanceRole)


@dataclass(frozen=True)
class NewUser:
    email: str
    full_name: str
    password: str
    role: InstanceRole


def ask_role() -> InstanceRole:
    """Роль инстанса; пустой ввод — `user`, неизвестная роль — спросить ещё раз."""
    while True:
        answer = input(f"Роль ({_ROLES}) [user]: ").strip().lower()
        if not answer:
            return InstanceRole.USER
        try:
            return InstanceRole(answer)
        except ValueError:
            print(f"Нет такой роли: {answer}", file=sys.stderr)


def ask_new_user() -> NewUser | None:
    """Данные пользователя из терминала; None — если пароли не совпали."""
    email = input("Email: ").strip()
    full_name = input("Имя: ").strip()
    role = ask_role()
    password = getpass.getpass("Пароль: ")
    if getpass.getpass("Пароль ещё раз: ") != password:
        print("Пароли не совпадают", file=sys.stderr)
        return None
    return NewUser(email=email, full_name=full_name, password=password, role=role)


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


async def _run(new_user: NewUser) -> int:
    async with get_sessionmaker()() as session:
        code = await create_user(
            session,
            email=new_user.email,
            full_name=new_user.full_name,
            password=new_user.password,
            role=new_user.role,
        )
        if code == 0:
            await session.commit()
    await get_engine().dispose()
    return code


def main() -> None:
    """Точка входа. Отделена от `create_user`, чтобы тест не поднимал настоящую сессию."""
    try:
        new_user = ask_new_user()
    except (KeyboardInterrupt, EOFError):
        print(file=sys.stderr)
        raise SystemExit(1) from None
    if new_user is None:
        raise SystemExit(1)
    raise SystemExit(asyncio.run(_run(new_user)))


if __name__ == "__main__":
    main()
