"""Входящие уведомления текущего пользователя."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.core.principal import CurrentPrincipal, WritePrincipal
from app.modules.notifications.schemas import NotificationPage, NotificationRead
from app.modules.notifications.service import NotificationService

router = APIRouter(prefix="/me/notifications", tags=["me"])


def get_notification_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NotificationService:
    return NotificationService(session)


Service = Annotated[NotificationService, Depends(get_notification_service)]


@router.get("", response_model=NotificationPage)
async def list_notifications(
    principal: CurrentPrincipal,
    service: Service,
    unread: Annotated[bool, Query(description="Только непрочитанные")] = False,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query()] = None,
) -> NotificationPage:
    return await service.inbox(principal.user_id, unread_only=unread, limit=limit, cursor=cursor)


@router.post("/{notification_id}/read", response_model=NotificationRead)
async def mark_read(
    notification_id: UUID, principal: WritePrincipal, service: Service
) -> NotificationRead:
    return NotificationRead.model_validate(
        await service.mark_read(principal.user_id, notification_id)
    )
