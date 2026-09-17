"""Контроль фикстуры: без него откат транзакции — предположение, а не факт."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import PROBE_TABLE


async def test_a_writes_a_row(db_session: AsyncSession) -> None:
    await db_session.execute(text(f"INSERT INTO {PROBE_TABLE} (value) VALUES ('от теста A')"))
    await db_session.commit()

    count = await db_session.scalar(text(f"SELECT count(*) FROM {PROBE_TABLE}"))
    assert count == 1


async def test_b_does_not_see_the_row_from_test_a(db_session: AsyncSession) -> None:
    count = await db_session.scalar(text(f"SELECT count(*) FROM {PROBE_TABLE}"))

    assert count == 0
