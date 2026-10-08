"""Запросы к notifications."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, notification: Notification) -> None:
        self._session.add(notification)
        await self._session.flush()

    async def get_own(self, notification_id: UUID, user_id: UUID) -> Notification | None:
        found: Notification | None = await self._session.scalar(
            select(Notification).where(
                Notification.id == notification_id, Notification.user_id == user_id
            )
        )
        return found

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        unread_only: bool,
        before: tuple[datetime, UUID] | None,
        limit: int,
    ) -> Sequence[Notification]:
        stmt = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit + 1)
        )
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        if before is not None:
            stmt = stmt.where(
                tuple_(Notification.created_at, Notification.id) < tuple_(*map(literal, before))
            )
        return (await self._session.scalars(stmt)).all()
