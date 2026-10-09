"""Таблицы этапа 3: ограничения, коллация и миграция, досоздающая статусы."""

import asyncio
import random
from collections.abc import Iterator
from uuid import UUID

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.fractional_index import DIGITS
from app.modules.labels.models import Label
from app.modules.states.models import WorkflowState
from app.modules.tasks.models import Task, TaskRelation
from app.modules.teams.models import Team
from app.modules.users.models import User
from tests.conftest import BACKEND_DIR, TEST_DATABASE_URL, _dsn
from tests.test_models_org import make_team, make_user, make_workspace


async def make_state(
    session: AsyncSession, team: Team, name: str = "Todo", *, is_default: bool = True
) -> WorkflowState:
    state = WorkflowState(
        workspace_id=team.workspace_id,
        team_id=team.id,
        name=name,
        type="unstarted",
        color="#e2e2e2",
        position=0,
        is_default=is_default,
    )
    session.add(state)
    await session.flush()
    return state


async def make_task(
    session: AsyncSession,
    team: Team,
    state: WorkflowState,
    creator: User,
    number: int,
    sort_order: str = "a0",
    **fields: object,
) -> Task:
    task = Task(
        workspace_id=team.workspace_id,
        team_id=team.id,
        number=number,
        title=f"Задача {number}",
        state_id=state.id,
        creator_id=creator.id,
        sort_order=sort_order,
        **fields,
    )
    session.add(task)
    await session.flush()
    return task


@pytest.fixture
async def world(db_session: AsyncSession) -> tuple[User, Team, WorkflowState]:
    user = await make_user(db_session)
    workspace = await make_workspace(db_session, user)
    team = await make_team(db_session, workspace)
    return user, team, await make_state(db_session, team)


class TestWorkflowState:
    async def test_one_default_per_team(
        self, db_session: AsyncSession, world: tuple[User, Team, WorkflowState]
    ) -> None:
        _, team, _ = world
        db_session.add(
            WorkflowState(
                workspace_id=team.workspace_id,
                team_id=team.id,
                name="Другой",
                type="backlog",
                color="#000000",
                position=1,
                is_default=True,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_name_is_case_insensitive_unique(
        self, db_session: AsyncSession, world: tuple[User, Team, WorkflowState]
    ) -> None:
        _, team, _ = world
        with pytest.raises(IntegrityError):
            await make_state(db_session, team, "TODO", is_default=False)


class TestTask:
    async def test_number_is_unique_within_team(
        self, db_session: AsyncSession, world: tuple[User, Team, WorkflowState]
    ) -> None:
        user, team, state = world
        await make_task(db_session, team, state, user, 1)
        with pytest.raises(IntegrityError):
            await make_task(db_session, team, state, user, 1)

    @pytest.mark.parametrize("priority", [-1, 5])
    async def test_priority_is_checked(
        self, db_session: AsyncSession, world: tuple[User, Team, WorkflowState], priority: int
    ) -> None:
        user, team, state = world
        with pytest.raises(IntegrityError):
            await make_task(db_session, team, state, user, 1, priority=priority)

    async def test_state_with_tasks_cannot_be_deleted(
        self, db_session: AsyncSession, world: tuple[User, Team, WorkflowState]
    ) -> None:
        user, team, state = world
        await make_task(db_session, team, state, user, 1)
        await db_session.delete(state)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_sort_order_compares_bytewise(
        self, db_session: AsyncSession, world: tuple[User, Team, WorkflowState]
    ) -> None:
        """Порядок базы обязан совпадать с порядком Python, иначе дробный индекс врёт."""
        user, team, state = world
        rng = random.Random(7)
        keys = {"a" + "".join(rng.choice(DIGITS) for _ in range(4)) for _ in range(40)}
        keys |= {"a0", "aZ", "aa", "aB", "ab", "Zz", "b00"}
        for number, key in enumerate(keys, start=1):
            await make_task(db_session, team, state, user, number, key)

        stored = await db_session.scalars(
            select(Task.sort_order).where(Task.team_id == team.id).order_by(Task.sort_order)
        )
        assert list(stored) == sorted(keys)

    async def test_sort_order_column_is_collated_c(self, db_session: AsyncSession) -> None:
        """Тест порядка выше на alpine-образе не упадёт и без COLLATE: musl сравнивает
        побайтово в любой локали. На glibc-сборке PostgreSQL (управляемые базы) — упадёт.
        Поэтому коллация колонки проверяется отдельно и напрямую."""
        collation = await db_session.scalar(
            text(
                "SELECT collation_name FROM information_schema.columns"
                " WHERE table_name = 'tasks' AND column_name = 'sort_order'"
            )
        )
        assert collation == "C"

    async def test_search_uses_gin_index(
        self, db_session: AsyncSession, world: tuple[User, Team, WorkflowState]
    ) -> None:
        """Выражение запроса совпадает с выражением индекса — иначе поиск идёт перебором."""
        from app.modules.tasks.models import search_document

        await db_session.execute(text("SET LOCAL enable_seqscan = off"))
        query = select(Task.id).where(
            search_document().op("@@")(text("websearch_to_tsquery('simple', 'логин')"))
        )
        compiled = query.compile(db_session.bind, compile_kwargs={"literal_binds": True})
        plan = (await db_session.execute(text(f"EXPLAIN {compiled}"))).scalars().all()
        assert any("idx_tasks_search" in line for line in plan), plan


class TestRelation:
    async def test_no_self_relation(
        self, db_session: AsyncSession, world: tuple[User, Team, WorkflowState]
    ) -> None:
        user, team, state = world
        task = await make_task(db_session, team, state, user, 1)
        db_session.add(
            TaskRelation(
                workspace_id=team.workspace_id,
                source_task_id=task.id,
                target_task_id=task.id,
                type="blocks",
                created_by=user.id,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestLabel:
    async def test_workspace_and_team_names_are_separate(
        self, db_session: AsyncSession, world: tuple[User, Team, WorkflowState]
    ) -> None:
        """Одно имя допустимо на уровне workspace и у команды, но не дважды на одном уровне."""
        _, team, _ = world
        db_session.add(Label(workspace_id=team.workspace_id, name="bug", color="#ff0000"))
        db_session.add(
            Label(workspace_id=team.workspace_id, team_id=team.id, name="Bug", color="#ff0000")
        )
        await db_session.flush()

        db_session.add(Label(workspace_id=team.workspace_id, name="BUG", color="#ff0000"))
        with pytest.raises(IntegrityError):
            await db_session.flush()


# --- Миграция на отдельной базе: основная тестовая уже на head. -----------------

MIGRATION_DB = "taskanline_test_migration"


@pytest.fixture
def migration_db(migrated_database: None) -> Iterator[Config]:
    dsn = _dsn(TEST_DATABASE_URL)
    maintenance = dsn.rsplit("/", 1)[0] + "/postgres"

    url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/" + MIGRATION_DB

    # База создаётся только при первом прогоне, а дальше чистится пересозданием схемы:
    # у пользователя тестов может не быть права CREATEDB, если базу завели заранее.
    async def _create_if_missing() -> None:
        connection = await asyncpg.connect(maintenance)
        try:
            exists = await connection.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", MIGRATION_DB
            )
            if not exists:
                await connection.execute(f'CREATE DATABASE "{MIGRATION_DB}"')
        finally:
            await connection.close()

    async def _reset() -> None:
        connection = await asyncpg.connect(_dsn(url))
        try:
            await connection.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public")
        finally:
            await connection.close()

    asyncio.run(_create_if_missing())
    asyncio.run(_reset())
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["database_url"] = url
    try:
        yield config
    finally:
        asyncio.run(_reset())


def test_migration_backfills_default_states(
    migration_db: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Команда, созданная до 0003, получает стандартный набор статусов."""
    url: str = migration_db.attributes["database_url"]
    # env.py берёт адрес из настроек приложения — подменяем имя базы там.
    monkeypatch.setenv("DB__NAME", MIGRATION_DB)
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        command.upgrade(migration_db, "0002_org")

        async def _seed() -> UUID:
            connection = await asyncpg.connect(_dsn(url))
            try:
                user = await connection.fetchval(
                    "INSERT INTO users (id, email, password_hash, full_name)"
                    " VALUES (gen_random_uuid(), 'a@example.com', 'x', 'A') RETURNING id"
                )
                workspace = await connection.fetchval(
                    "INSERT INTO workspaces (id, name, slug, created_by)"
                    " VALUES (gen_random_uuid(), 'Acme', 'acme', $1) RETURNING id",
                    user,
                )
                team: UUID = await connection.fetchval(
                    "INSERT INTO teams (id, workspace_id, key, name)"
                    " VALUES (gen_random_uuid(), $1, 'ENG', 'Eng') RETURNING id",
                    workspace,
                )
                return team
            finally:
                await connection.close()

        team_id = asyncio.run(_seed())
        command.upgrade(migration_db, "head")

        async def _states() -> list[tuple[str, str, bool, int]]:
            connection = await asyncpg.connect(_dsn(url))
            try:
                rows = await connection.fetch(
                    "SELECT name, type, is_default, position FROM workflow_states"
                    " WHERE team_id = $1 ORDER BY position",
                    team_id,
                )
                return [tuple(row) for row in rows]
            finally:
                await connection.close()

        assert asyncio.run(_states()) == [
            ("Backlog", "backlog", False, 0),
            ("Todo", "unstarted", True, 1),
            ("In Progress", "started", False, 2),
            ("Done", "completed", False, 3),
            ("Canceled", "canceled", False, 4),
        ]

        command.downgrade(migration_db, "0002_org")
    finally:
        get_settings.cache_clear()
