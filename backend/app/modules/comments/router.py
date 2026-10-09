"""HTTP-слой комментариев."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.core.permissions import AccessContext, AccessTarget, Permission, require_permission
from app.modules.comments.schemas import CommentCreate, CommentPage, CommentRead, CommentUpdate
from app.modules.comments.service import CommentService

task_comments_router = APIRouter(prefix="/tasks/{task_id}/comments", tags=["comments"])
router = APIRouter(prefix="/comments", tags=["comments"])


def get_comment_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CommentService:
    return CommentService(session)


Service = Annotated[CommentService, Depends(get_comment_service)]


def _can(permission: Permission, on: AccessTarget) -> Any:
    return Depends(require_permission(permission, on=on))


CanRead = Annotated[AccessContext, _can(Permission.TASK_READ, "task")]
CanComment = Annotated[AccessContext, _can(Permission.COMMENT_CREATE, "task")]
# «Автор или admin» проверяет сервис: одной минимальной ролью это не выражается.
CanEdit = Annotated[AccessContext, _can(Permission.COMMENT_EDIT, "comment")]


@task_comments_router.get("", response_model=CommentPage)
async def list_comments(
    task_id: str,
    ctx: CanRead,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query()] = None,
) -> CommentPage:
    return await service.list_for_task(ctx, limit=limit, cursor=cursor)


@task_comments_router.post("", response_model=CommentRead, status_code=201)
async def create_comment(
    task_id: str, payload: CommentCreate, ctx: CanComment, service: Service
) -> CommentRead:
    (read,) = await service.present([await service.create(ctx, payload)])
    return read


@router.patch("/{comment_id}", response_model=CommentRead)
async def update_comment(
    comment_id: str, payload: CommentUpdate, ctx: CanEdit, service: Service
) -> CommentRead:
    (read,) = await service.present([await service.update(ctx, payload)])
    return read


@router.delete("/{comment_id}", status_code=204)
async def delete_comment(comment_id: str, ctx: CanEdit, service: Service) -> None:
    await service.delete(ctx)
