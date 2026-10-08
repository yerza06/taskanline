"""История изменений задачи."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.core.permissions import AccessContext, Permission, require_permission
from app.modules.activities.schemas import ActivityPage
from app.modules.activities.service import ActivityService

router = APIRouter(prefix="/tasks/{task_id}/activities", tags=["tasks"])

CanRead = Annotated[AccessContext, Depends(require_permission(Permission.TASK_READ, on="task"))]


@router.get("", response_model=ActivityPage)
async def list_activities(
    task_id: str,
    ctx: CanRead,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query()] = None,
) -> ActivityPage:
    """От новых событий к старым. История удалённой задачи тоже доступна."""
    return await ActivityService(session).list_for_task(
        ctx.workspace_id, ctx.object_id, limit=limit, cursor=cursor
    )
