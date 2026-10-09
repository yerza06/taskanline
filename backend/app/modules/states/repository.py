"""Запросы к workflow_states."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import and_, delete, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.states.models import WorkflowState


class StateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_team(self, team_id: UUID) -> Sequence[WorkflowState]:
        stmt = (
            select(WorkflowState)
            .where(WorkflowState.team_id == team_id)
            .order_by(WorkflowState.position, WorkflowState.created_at, WorkflowState.id)
        )
        return (await self._session.scalars(stmt)).all()

    async def get_in_workspace(self, state_id: UUID, workspace_id: UUID) -> WorkflowState | None:
        state: WorkflowState | None = await self._session.scalar(
            select(WorkflowState).where(
                WorkflowState.id == state_id, WorkflowState.workspace_id == workspace_id
            )
        )
        return state

    async def get_in_team(self, state_id: UUID, team_id: UUID) -> WorkflowState | None:
        state: WorkflowState | None = await self._session.scalar(
            select(WorkflowState).where(
                WorkflowState.id == state_id, WorkflowState.team_id == team_id
            )
        )
        return state

    async def get_many(self, state_ids: Sequence[UUID]) -> Sequence[WorkflowState]:
        if not state_ids:
            return []
        return (
            await self._session.scalars(
                select(WorkflowState).where(WorkflowState.id.in_(state_ids))
            )
        ).all()

    async def default_for_team(self, team_id: UUID) -> WorkflowState | None:
        state: WorkflowState | None = await self._session.scalar(
            select(WorkflowState).where(
                WorkflowState.team_id == team_id, WorkflowState.is_default.is_(True)
            )
        )
        return state

    async def name_taken(self, team_id: UUID, name: str, *, exclude: UUID | None = None) -> bool:
        condition = and_(
            WorkflowState.team_id == team_id, func.lower(WorkflowState.name) == name.lower()
        )
        if exclude is not None:
            condition = and_(condition, WorkflowState.id != exclude)
        return bool(await self._session.scalar(select(exists().where(condition))))

    async def next_position(self, team_id: UUID) -> int:
        current = await self._session.scalar(
            select(func.max(WorkflowState.position)).where(WorkflowState.team_id == team_id)
        )
        return 0 if current is None else current + 1

    async def clear_default(self, team_id: UUID) -> None:
        """Снять флаг до установки нового: частичный уникальный индекс не даст двух."""
        await self._session.execute(
            update(WorkflowState)
            .where(WorkflowState.team_id == team_id, WorkflowState.is_default.is_(True))
            .values(is_default=False)
        )

    async def add(self, state: WorkflowState) -> WorkflowState:
        self._session.add(state)
        await self._session.flush()
        return state

    async def delete(self, state_id: UUID, team_id: UUID) -> None:
        await self._session.execute(
            delete(WorkflowState).where(
                WorkflowState.id == state_id, WorkflowState.team_id == team_id
            )
        )
