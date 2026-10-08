"""Уведомления: создание из других модулей и входящие текущего пользователя."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import NotificationType
from app.core.errors import ApiError
from app.core.pagination import decode_cursor, paginate
from app.modules.notifications.models import Notification
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import NotificationPage, NotificationRead


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._notifications = NotificationRepository(session)

    async def notify(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        kind: NotificationType,
        actor_id: UUID,
        task_id: UUID | None = None,
        comment_id: UUID | None = None,
    ) -> None:
        """Без commit — в транзакции события. О собственных действиях не уведомляем."""
        if user_id == actor_id:
            return
        await self._notifications.add(
            Notification(
                workspace_id=workspace_id,
                user_id=user_id,
                type=kind,
                actor_id=actor_id,
                task_id=task_id,
                comment_id=comment_id,
            )
        )

    async def inbox(
        self, user_id: UUID, *, unread_only: bool, limit: int, cursor: str | None
    ) -> NotificationPage:
        before = None
        if cursor is not None:
            created_at, notification_id = decode_cursor(cursor, 2)
            try:
                before = (datetime.fromisoformat(created_at), UUID(notification_id))
            except ValueError as error:
                raise ApiError(400, "invalid_cursor", "Курсор повреждён или устарел") from error
        rows = await self._notifications.list_for_user(
            user_id, unread_only=unread_only, before=before, limit=limit
        )
        items, next_cursor, has_more = paginate(
            rows, limit, lambda row: (row.created_at.isoformat(), row.id)
        )
        return NotificationPage(
            items=[NotificationRead.model_validate(item) for item in items],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def mark_read(self, user_id: UUID, notification_id: UUID) -> Notification:
        """Чужое уведомление неотличимо от несуществующего — 404."""
        notification = await self._notifications.get_own(notification_id, user_id)
        if notification is None:
            raise ApiError(404, "notification_not_found", "Уведомление не найдено")
        if notification.read_at is None:
            notification.read_at = datetime.now(UTC)
            await self._session.commit()
        return notification
