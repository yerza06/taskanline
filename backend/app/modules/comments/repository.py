"""Запросы к comments и comment_mentions."""

from collections import defaultdict
from collections.abc import Collection, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.comments.models import Comment, CommentMention


class CommentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, comment: Comment) -> Comment:
        self._session.add(comment)
        await self._session.flush()
        return comment

    async def get_in_workspace(self, comment_id: UUID, workspace_id: UUID) -> Comment | None:
        comment: Comment | None = await self._session.scalar(
            select(Comment).where(Comment.id == comment_id, Comment.workspace_id == workspace_id)
        )
        return comment

    async def list_for_task(
        self,
        task_id: UUID,
        workspace_id: UUID,
        *,
        after: tuple[datetime, UUID] | None,
        limit: int,
    ) -> Sequence[Comment]:
        """По возрастанию времени — так читается обсуждение."""
        stmt = (
            select(Comment)
            .where(
                Comment.task_id == task_id,
                Comment.workspace_id == workspace_id,
                Comment.deleted_at.is_(None),
            )
            .order_by(Comment.created_at, Comment.id)
            .limit(limit + 1)
        )
        if after is not None:
            stmt = stmt.where(tuple_(Comment.created_at, Comment.id) > tuple_(*map(literal, after)))
        return (await self._session.scalars(stmt)).all()

    async def mentions_of(self, comment_ids: Collection[UUID]) -> dict[UUID, list[UUID]]:
        grouped: dict[UUID, list[UUID]] = defaultdict(list)
        if not comment_ids:
            return grouped
        rows = await self._session.execute(
            select(CommentMention.comment_id, CommentMention.user_id)
            .where(CommentMention.comment_id.in_(comment_ids))
            .order_by(CommentMention.user_id)
        )
        for comment_id, user_id in rows.tuples():
            grouped[comment_id].append(user_id)
        return grouped

    async def add_mentions(self, comment: Comment, user_ids: Collection[UUID]) -> None:
        for user_id in user_ids:
            self._session.add(
                CommentMention(
                    comment_id=comment.id, user_id=user_id, workspace_id=comment.workspace_id
                )
            )
        await self._session.flush()
