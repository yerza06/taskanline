"""Запросы к activities. Только вставка и чтение: лента append-only."""

from collections.abc import Collection, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.activities.models import Activity


class ActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, activity: Activity) -> None:
        self._session.add(activity)
        await self._session.flush()

    async def list_for_task(
        self,
        task_id: UUID,
        workspace_id: UUID,
        *,
        before: tuple[datetime, UUID] | None,
        limit: int,
    ) -> Sequence[Activity]:
        """От новых к старым; `before` — курсор `(created_at, id)` последней выданной."""
        stmt = (
            select(Activity)
            .where(Activity.task_id == task_id, Activity.workspace_id == workspace_id)
            .order_by(Activity.created_at.desc(), Activity.id.desc())
            .limit(limit + 1)
        )
        if before is not None:
            stmt = stmt.where(
                tuple_(Activity.created_at, Activity.id) < tuple_(*map(literal, before))
            )
        return (await self._session.scalars(stmt)).all()

    async def last_at_by_workspace(self, ids: Collection[UUID]) -> dict[UUID, datetime]:
        """Время последнего изменения задач в каждом пространстве."""
        if not ids:
            return {}
        rows = await self._session.execute(
            select(Activity.workspace_id, func.max(Activity.created_at))
            .where(Activity.workspace_id.in_(ids))
            .group_by(Activity.workspace_id)
        )
        return dict(rows.tuples().all())
