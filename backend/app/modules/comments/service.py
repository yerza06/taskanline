"""Комментарии к задачам и упоминания в них.

Упоминание — `@email` в тексте. Оно материализуется в `comment_mentions` и рождает
уведомление, только если упомянутый видит задачу: иначе уведомление раскрыло бы
задачу человеку без доступа к ней.
"""

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ActivityType, NotificationType
from app.core.errors import ApiError
from app.core.pagination import decode_cursor, paginate
from app.core.permissions import AccessContext, EffectiveRole, compute_effective_role, load_access
from app.modules.comments.models import Comment
from app.modules.comments.repository import CommentRepository
from app.modules.comments.schemas import CommentCreate, CommentPage, CommentRead, CommentUpdate
from app.modules.notifications.service import NotificationService
from app.modules.tasks.models import Task
from app.modules.tasks.service import TaskService
from app.modules.users.service import UserService

MENTION = re.compile(r"(?<![\w.+-])@([A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
# Больше упоминаний в одном комментарии не разбирается: это уже рассылка.
MAX_MENTIONS = 50


def parse_mentions(body: str) -> list[str]:
    """Адреса из `@email` в порядке появления, без повторов, в нижнем регистре."""
    seen: dict[str, None] = {}
    for match in MENTION.finditer(body):
        seen.setdefault(match.group(1).lower().rstrip("."), None)
    return list(seen)[:MAX_MENTIONS]


def _not_found() -> ApiError:
    return ApiError(404, "comment_not_found", "Комментарий не найден")


class CommentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._comments = CommentRepository(session)
        self._tasks = TaskService(session)
        self._notifications = NotificationService(session)

    async def list_for_task(
        self, ctx: AccessContext, *, limit: int, cursor: str | None
    ) -> CommentPage:
        task = await self._tasks.get(ctx)
        after = None
        if cursor is not None:
            created_at, comment_id = decode_cursor(cursor, 2)
            try:
                after = (datetime.fromisoformat(created_at), UUID(comment_id))
            except ValueError as error:
                raise ApiError(400, "invalid_cursor", "Курсор повреждён или устарел") from error
        rows = await self._comments.list_for_task(
            task.id, ctx.workspace_id, after=after, limit=limit
        )
        items, next_cursor, has_more = paginate(
            rows, limit, lambda row: (row.created_at.isoformat(), row.id)
        )
        return CommentPage(
            items=await self.present(items), next_cursor=next_cursor, has_more=has_more
        )

    async def create(self, ctx: AccessContext, data: CommentCreate) -> Comment:
        task = await self._tasks.get(ctx)
        if data.parent_id is not None:
            parent = await self._comments.get_in_workspace(data.parent_id, ctx.workspace_id)
            if parent is None or parent.deleted_at is not None or parent.task_id != task.id:
                raise ApiError(
                    400,
                    "invalid_parent_comment",
                    "Отвечать можно только на комментарий этой же задачи",
                    {"parent_id": str(data.parent_id)},
                )
            if parent.parent_id is not None:
                raise ApiError(
                    400, "comment_reply_depth", "Ответы — только на комментарий верхнего уровня"
                )

        now = datetime.now(UTC)
        comment = await self._comments.add(
            Comment(
                workspace_id=ctx.workspace_id,
                task_id=task.id,
                author_id=ctx.principal.user_id,
                author_token_id=ctx.principal.token_id,
                parent_id=data.parent_id,
                body=data.body,
                created_at=now,
                updated_at=now,
            )
        )
        await self._mention(ctx, task, comment, already=set())
        await self._tasks.record(ctx, task, ActivityType.COMMENTED, {"comment_id": str(comment.id)})
        await self._session.commit()
        return comment

    async def update(self, ctx: AccessContext, data: CommentUpdate) -> Comment:
        comment, task = await self._live(ctx)
        if comment.author_id != ctx.principal.user_id:
            raise ApiError(403, "not_comment_author", "Изменить комментарий может только автор")
        if data.body != comment.body:
            comment.body = data.body
            comment.updated_at = datetime.now(UTC)
            mentioned = await self._comments.mentions_of([comment.id])
            await self._mention(ctx, task, comment, already=set(mentioned.get(comment.id, [])))
            await self._session.commit()
        return comment

    async def delete(self, ctx: AccessContext) -> None:
        comment, _ = await self._live(ctx)
        if comment.author_id != ctx.principal.user_id and ctx.role < EffectiveRole.ADMIN:
            raise ApiError(
                403,
                "insufficient_role",
                "Чужой комментарий удаляет только администратор",
                {"required": "admin"},
            )
        comment.deleted_at = datetime.now(UTC)
        await self._session.commit()

    async def present(self, comments: Sequence[Comment]) -> list[CommentRead]:
        mentions = await self._comments.mentions_of([comment.id for comment in comments])
        return [
            CommentRead(
                id=comment.id,
                task_id=comment.task_id,
                author_id=comment.author_id,
                author_token_id=comment.author_token_id,
                parent_id=comment.parent_id,
                body=comment.body,
                mention_ids=mentions.get(comment.id, []),
                created_at=comment.created_at,
                updated_at=comment.updated_at,
            )
            for comment in comments
        ]

    async def _live(self, ctx: AccessContext) -> tuple[Comment, Task]:
        """Комментарий и его задача; удалённое — то же, что несуществующее."""
        comment = await self._comments.get_in_workspace(ctx.object_id, ctx.workspace_id)
        if comment is None or comment.deleted_at is not None:
            raise _not_found()
        task = await self._tasks.find_live(comment.task_id, ctx.workspace_id)
        if task is None:
            raise _not_found()
        return comment, task

    async def _mention(
        self, ctx: AccessContext, task: Task, comment: Comment, *, already: set[UUID]
    ) -> None:
        """Материализовать новые упоминания и уведомить упомянутых."""
        emails = parse_mentions(comment.body)
        users = await UserService(self._session).find_many_by_email(emails)
        fresh: list[UUID] = []
        for user in users:
            if user.id in already or user.id == ctx.principal.user_id:
                continue
            row = await load_access(self._session, user.id, "task", task.id)
            role = compute_effective_role(row) if row is not None else None
            if role is not None and role >= EffectiveRole.VIEWER:
                fresh.append(user.id)
        await self._comments.add_mentions(comment, fresh)
        for user_id in fresh:
            await self._notifications.notify(
                workspace_id=task.workspace_id,
                user_id=user_id,
                kind=NotificationType.MENTIONED,
                actor_id=ctx.principal.user_id,
                task_id=task.id,
                comment_id=comment.id,
            )
