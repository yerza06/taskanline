"""Запросы к журналу аудита. Только вставка и чтение: правки и удаления нет вовсе."""

from collections.abc import Sequence
from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.models import AdminAuditLog
from app.modules.admin.schemas import AuditFilters


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: AdminAuditLog) -> None:
        self._session.add(entry)
        await self._session.flush()

    async def page(
        self, filters: AuditFilters, *, after: tuple[datetime, UUID] | None, limit: int
    ) -> Sequence[AdminAuditLog]:
        """Новые первыми. Даты — дни по UTC включительно."""
        stmt = select(AdminAuditLog)
        if filters.actor_id is not None:
            stmt = stmt.where(AdminAuditLog.actor_id == filters.actor_id)
        if filters.action is not None:
            stmt = stmt.where(AdminAuditLog.action == filters.action)
        if filters.target_type is not None:
            stmt = stmt.where(AdminAuditLog.target_type == filters.target_type)
        if filters.target_id is not None:
            stmt = stmt.where(AdminAuditLog.target_id == filters.target_id)
        if filters.date_from is not None:
            start = datetime.combine(filters.date_from, time.min, tzinfo=UTC)
            stmt = stmt.where(AdminAuditLog.created_at >= start)
        if filters.date_to is not None:
            end = datetime.combine(filters.date_to, time.min, tzinfo=UTC) + timedelta(days=1)
            stmt = stmt.where(AdminAuditLog.created_at < end)
        if after is not None:
            stmt = stmt.where(
                tuple_(AdminAuditLog.created_at, AdminAuditLog.id) < tuple_(*map(literal, after))
            )
        stmt = stmt.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
        return (await self._session.scalars(stmt.limit(limit + 1))).all()
