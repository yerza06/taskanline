"""Запись и чтение истории изменений.

Запись — без commit: она обязана попасть в ту же транзакцию, что и само изменение,
иначе при сбое история разойдётся с данными.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ActivityType
from app.core.errors import ApiError
from app.core.pagination import decode_cursor, paginate
from app.core.principal import Principal
from app.modules.activities.models import Activity
from app.modules.activities.repository import ActivityRepository
from app.modules.activities.schemas import ActivityPage, ActivityRead


class ActivityService:
    def __init__(self, session: AsyncSession) -> None:
        self._activities = ActivityRepository(session)

    async def record(
        self,
        *,
        workspace_id: UUID,
        task_id: UUID,
        actor: Principal,
        kind: ActivityType,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await self._activities.add(
            Activity(
                workspace_id=workspace_id,
                task_id=task_id,
                actor_id=actor.user_id,
                # Агент действует от имени человека; токен отличает его в истории.
                actor_token_id=actor.token_id,
                type=kind,
                payload=payload or {},
            )
        )

    async def list_for_task(
        self, workspace_id: UUID, task_id: UUID, *, limit: int, cursor: str | None
    ) -> ActivityPage:
        before = None
        if cursor is not None:
            created_at, activity_id = decode_cursor(cursor, 2)
            try:
                before = (datetime.fromisoformat(created_at), UUID(activity_id))
            except ValueError as error:
                raise ApiError(400, "invalid_cursor", "Курсор повреждён или устарел") from error
        rows = await self._activities.list_for_task(
            task_id, workspace_id, before=before, limit=limit
        )
        items, next_cursor, has_more = paginate(
            rows, limit, lambda row: (row.created_at.isoformat(), row.id)
        )
        return ActivityPage(
            items=[ActivityRead.model_validate(item) for item in items],
            next_cursor=next_cursor,
            has_more=has_more,
        )
