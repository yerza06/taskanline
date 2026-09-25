"""Запросы к workspaces и workspace_members. Про HTTP здесь ничего не известно."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import and_, delete, exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import WorkspaceRole
from app.modules.users.models import User
from app.modules.workspaces.models import Workspace, WorkspaceMember


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, workspace_id: UUID) -> Workspace | None:
        return await self._session.get(Workspace, workspace_id)

    async def slug_taken(self, slug: str, *, exclude: UUID | None = None) -> bool:
        """Сравнение регистронезависимо: колонка CITEXT."""
        condition = Workspace.slug == slug
        if exclude is not None:
            condition = and_(condition, Workspace.id != exclude)
        return bool(await self._session.scalar(select(exists().where(condition))))

    async def create(self, *, name: str, slug: str, created_by: UUID) -> Workspace:
        workspace = Workspace(name=name, slug=slug, created_by=created_by)
        self._session.add(workspace)
        await self._session.flush()
        return workspace

    async def list_for_user(self, user_id: UUID) -> Sequence[Workspace]:
        stmt = (
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.name, Workspace.id)
        )
        return (await self._session.scalars(stmt)).all()

    async def delete(self, workspace_id: UUID) -> None:
        """Всё содержимое уходит каскадом в самой базе."""
        await self._session.execute(delete(Workspace).where(Workspace.id == workspace_id))

    async def get_member(self, workspace_id: UUID, user_id: UUID) -> WorkspaceMember | None:
        member: WorkspaceMember | None = await self._session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id
            )
        )
        return member

    async def get_member_with_user(
        self, workspace_id: UUID, user_id: UUID
    ) -> tuple[WorkspaceMember, User] | None:
        stmt = (
            select(WorkspaceMember, User)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
        )
        row = (await self._session.execute(stmt)).tuples().one_or_none()
        return row

    async def list_members(self, workspace_id: UUID) -> list[tuple[WorkspaceMember, User]]:
        stmt = (
            select(WorkspaceMember, User)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(User.full_name, User.id)
        )
        return list((await self._session.execute(stmt)).tuples())

    async def add_member(
        self, *, workspace_id: UUID, user_id: UUID, role: WorkspaceRole
    ) -> WorkspaceMember:
        member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
        self._session.add(member)
        await self._session.flush()
        return member

    async def add_member_if_absent(
        self, *, workspace_id: UUID, user_id: UUID, role: WorkspaceRole
    ) -> WorkspaceMember:
        """Вставка без гонки: `ON CONFLICT DO NOTHING` вместо «проверил — вставил».

        Два конкурентных accept одного и того же членства раньше оба проходили
        `get_member is None` и падали вторым `INSERT` в `IntegrityError` на
        `idx_ws_members_unique`. Здесь конфликт гасится на уровне базы, а не ловится
        через исключение — после него строка перечитывается и уже существует.
        """
        stmt = (
            pg_insert(WorkspaceMember)
            .values(workspace_id=workspace_id, user_id=user_id, role=role)
            .on_conflict_do_nothing(index_elements=["workspace_id", "user_id"])
        )
        await self._session.execute(stmt)
        await self._session.flush()
        member = await self.get_member(workspace_id, user_id)
        assert member is not None, "строка обязана существовать после INSERT ... ON CONFLICT"
        return member

    async def count_owners_locked(self, workspace_id: UUID) -> int:
        """Владельцы под `FOR UPDATE`.

        Без блокировки два владельца, одновременно понижающие друг друга, оба
        увидели бы «нас двое» — и пространство осталось бы без владельца.
        """
        stmt = (
            select(WorkspaceMember.id)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role == WorkspaceRole.OWNER,
            )
            .with_for_update()
        )
        return len((await self._session.scalars(stmt)).all())

    async def delete_member(self, member: WorkspaceMember) -> None:
        """Членства в командах и проектах уходят каскадом по составному ключу."""
        await self._session.delete(member)
        await self._session.flush()

    async def memberships_of(self, user_id: UUID) -> Sequence[WorkspaceMember]:
        stmt = (
            select(WorkspaceMember)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(WorkspaceMember.created_at)
        )
        return (await self._session.scalars(stmt)).all()
