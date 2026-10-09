"""Запросы к labels и task_labels."""

from collections.abc import Collection, Sequence
from uuid import UUID

from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.labels.models import Label, TaskLabel


class LabelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for(self, workspace_id: UUID, team_ids: Collection[UUID]) -> Sequence[Label]:
        """Метки workspace и перечисленных команд."""
        stmt = (
            select(Label)
            .where(
                Label.workspace_id == workspace_id,
                or_(Label.team_id.is_(None), Label.team_id.in_(team_ids)),
            )
            .order_by(Label.team_id.is_not(None), func.lower(Label.name), Label.id)
        )
        return (await self._session.scalars(stmt)).all()

    async def get_in_workspace(self, label_id: UUID, workspace_id: UUID) -> Label | None:
        label: Label | None = await self._session.scalar(
            select(Label).where(Label.id == label_id, Label.workspace_id == workspace_id)
        )
        return label

    async def get_many(self, label_ids: Collection[UUID], workspace_id: UUID) -> Sequence[Label]:
        if not label_ids:
            return []
        stmt = select(Label).where(Label.id.in_(label_ids), Label.workspace_id == workspace_id)
        return (await self._session.scalars(stmt)).all()

    async def name_taken(
        self, workspace_id: UUID, team_id: UUID | None, name: str, *, exclude: UUID | None = None
    ) -> bool:
        same_level = Label.team_id.is_(None) if team_id is None else Label.team_id == team_id
        condition = and_(
            Label.workspace_id == workspace_id, same_level, func.lower(Label.name) == name.lower()
        )
        if exclude is not None:
            condition = and_(condition, Label.id != exclude)
        return bool(await self._session.scalar(select(exists().where(condition))))

    async def add(self, label: Label) -> Label:
        self._session.add(label)
        await self._session.flush()
        return label

    async def delete(self, label_id: UUID, workspace_id: UUID) -> None:
        await self._session.execute(
            delete(Label).where(Label.id == label_id, Label.workspace_id == workspace_id)
        )

    async def labels_of_tasks(self, task_ids: Collection[UUID]) -> list[tuple[UUID, Label]]:
        if not task_ids:
            return []
        stmt = (
            select(TaskLabel.task_id, Label)
            .join(Label, Label.id == TaskLabel.label_id)
            .where(TaskLabel.task_id.in_(task_ids))
            .order_by(func.lower(Label.name), Label.id)
        )
        return list((await self._session.execute(stmt)).tuples())

    async def attach(self, workspace_id: UUID, task_id: UUID, label_ids: Collection[UUID]) -> None:
        for label_id in label_ids:
            self._session.add(
                TaskLabel(workspace_id=workspace_id, task_id=task_id, label_id=label_id)
            )
        await self._session.flush()

    async def detach(self, task_id: UUID, label_ids: Collection[UUID]) -> None:
        if label_ids:
            await self._session.execute(
                delete(TaskLabel).where(
                    TaskLabel.task_id == task_id, TaskLabel.label_id.in_(label_ids)
                )
            )
