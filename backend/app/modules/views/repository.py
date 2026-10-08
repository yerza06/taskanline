"""Запросы к views."""

from collections.abc import Collection, Sequence
from uuid import UUID

from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ViewScope
from app.modules.views.models import View


class ViewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, view_id: UUID) -> View | None:
        """По одному id: workspace ещё неизвестен — права проверяются сразу после."""
        return await self._session.get(View, view_id)

    async def add(self, view: View) -> View:
        self._session.add(view)
        await self._session.flush()
        return view

    async def delete(self, view: View) -> None:
        await self._session.execute(
            delete(View).where(View.id == view.id, View.workspace_id == view.workspace_id)
        )

    async def next_position(
        self, workspace_id: UUID, scope: ViewScope, owner_id: UUID | None, team_id: UUID | None
    ) -> int:
        stmt = select(func.max(View.position)).where(
            View.workspace_id == workspace_id, View.scope == scope
        )
        if scope == ViewScope.USER:
            stmt = stmt.where(View.owner_id == owner_id)
        elif scope == ViewScope.TEAM:
            stmt = stmt.where(View.team_id == team_id)
        current = await self._session.scalar(stmt)
        return 0 if current is None else current + 1

    async def list_visible(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        team_ids: Collection[UUID],
        include_workspace: bool,
    ) -> Sequence[View]:
        """Личные — свои, командные — видимых команд, общие — если не гость."""
        visible = [
            and_(View.scope == ViewScope.USER, View.owner_id == user_id),
            and_(View.scope == ViewScope.TEAM, View.team_id.in_(team_ids)),
        ]
        if include_workspace:
            visible.append(View.scope == ViewScope.WORKSPACE)
        section = case(
            (View.scope == ViewScope.USER, 0), (View.scope == ViewScope.TEAM, 1), else_=2
        )
        stmt = (
            select(View)
            .where(View.workspace_id == workspace_id, or_(*visible))
            .order_by(section, View.team_id, View.position, View.created_at, View.id)
        )
        return (await self._session.scalars(stmt)).all()
