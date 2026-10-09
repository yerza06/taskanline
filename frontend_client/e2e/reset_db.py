"""База e2e-прогона: `reset` — пересоздать пустой, `open` — после миграций открыть
регистрацию (миграция ставит `invite_only`, а сценарии заводят несколько человек).

Подключение — из тех же `DB__*`, что у приложения; имя базы задаёт `DB__NAME`.
Трогается только база с суффиксом `_e2e` — рабочую сюда случайно не передать.
"""

import asyncio
import sys

import asyncpg

from app.core.config import get_settings


async def main(command: str) -> None:
    db = get_settings().db
    if not db.name.endswith("_e2e"):
        raise SystemExit(f"Отказ: {db.name} — не база e2e")
    if command == "open":
        connection = await asyncpg.connect(
            user=db.user,
            password=db.password.get_secret_value(),
            host=db.host,
            port=db.port,
            database=db.name,
        )
        try:
            await connection.execute("UPDATE instance_settings SET registration_mode = 'open'")
        finally:
            await connection.close()
        return
    connection = await asyncpg.connect(
        user=db.user,
        password=db.password.get_secret_value(),
        host=db.host,
        port=db.port,
        database="postgres",
    )
    try:
        await connection.execute(f'DROP DATABASE IF EXISTS "{db.name}" WITH (FORCE)')
        await connection.execute(f'CREATE DATABASE "{db.name}"')
    finally:
        await connection.close()


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "reset"))
