"""Пересоздать базу e2e-прогона: каждый прогон Playwright начинается с чистого листа.

Подключение — из тех же `DB__*`, что у приложения; имя базы задаёт `DB__NAME`.
Пересоздаётся только база с суффиксом `_e2e` — рабочую сюда случайно не передать.
"""

import asyncio

import asyncpg

from app.core.config import get_settings


async def main() -> None:
    db = get_settings().db
    if not db.name.endswith("_e2e"):
        raise SystemExit(f"Отказ: {db.name} — не база e2e")
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


asyncio.run(main())
