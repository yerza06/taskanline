"""Аварийное управление инстансом из командной строки.

    uv run python -m app.admin grant --email ivan@example.com --role superadmin

Команда существует для одного случая: единственный superadmin потерян, а поднять
себе роль через API невозможно по определению — прав на это как раз и нет.
Поэтому она работает с базой напрямую и не спрашивает сессию; доступ к ней
равносилен доступу к серверу.

Аргументы разбирает argparse: отдельная зависимость на CLI бэкенду не нужна,
typer появится в `cli/` на этапе 7.
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_engine, get_sessionmaker
from app.core.enums import InstanceRole
from app.modules.users.repository import UserRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.admin", description="Управление инстансом")
    commands = parser.add_subparsers(dest="command", required=True)

    grant_command = commands.add_parser("grant", help="Назначить пользователю роль инстанса")
    grant_command.add_argument("--email", required=True, help="Адрес существующего пользователя")
    grant_command.add_argument(
        "--role",
        required=True,
        type=InstanceRole,
        choices=list(InstanceRole),
        help="superadmin | admin | support | user",
    )
    return parser


async def grant(session: AsyncSession, *, email: str, role: InstanceRole) -> int:
    """Код возврата: 0 — роль назначена, 1 — такого пользователя нет."""
    user = await UserRepository(session).get_by_email(email.strip().lower())
    if user is None:
        print(f"Пользователь {email} не найден", file=sys.stderr)
        return 1

    previous = user.role
    user.role = role
    user.updated_at = datetime.now(UTC)
    await session.flush()
    print(f"{user.email}: {previous} → {role}")
    return 0


async def _run(args: argparse.Namespace) -> int:
    async with get_sessionmaker()() as session:
        code = await grant(session, email=args.email, role=args.role)
        if code == 0:
            await session.commit()
    await get_engine().dispose()
    return code


def main() -> None:
    """Точка входа. Отделена от `grant`, чтобы тест не поднимал настоящую сессию."""
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
