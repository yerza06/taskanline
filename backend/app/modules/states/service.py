"""Бизнес-правила workflow-статусов."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import StateType
from app.core.errors import ApiError
from app.core.permissions import AccessContext
from app.modules.states.models import WorkflowState
from app.modules.states.repository import StateRepository
from app.modules.states.schemas import StateCreate, StateUpdate

# Стандартный набор новой команды: (name, type, color, is_default); порядок — position.
DEFAULT_STATES = [
    ("Backlog", StateType.BACKLOG, "#bec2c8", False),
    ("Todo", StateType.UNSTARTED, "#e2e2e2", True),
    ("In Progress", StateType.STARTED, "#f2c94c", False),
    ("Done", StateType.COMPLETED, "#5e6ad2", False),
    ("Canceled", StateType.CANCELED, "#95a2b3", False),
]


def _name_taken(name: str) -> ApiError:
    return ApiError(409, "state_name_taken", "Статус с таким названием уже есть", {"name": name})


def _is_default() -> ApiError:
    return ApiError(
        400,
        "state_is_default",
        "Это статус по умолчанию: сначала назначьте по умолчанию другой статус",
    )


class StateService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._states = StateRepository(session)

    async def create_defaults(self, workspace_id: UUID, team_id: UUID) -> None:
        """Стандартный набор при создании команды. Без commit — в транзакции команды."""
        for position, (name, kind, color, is_default) in enumerate(DEFAULT_STATES):
            await self._states.add(
                WorkflowState(
                    workspace_id=workspace_id,
                    team_id=team_id,
                    name=name,
                    type=kind,
                    color=color,
                    position=position,
                    is_default=is_default,
                )
            )

    async def list_for_team(self, ctx: AccessContext) -> Sequence[WorkflowState]:
        return await self._states.list_for_team(ctx.team)

    async def get(self, ctx: AccessContext, state_id: UUID) -> WorkflowState:
        state = await self._states.get_in_workspace(state_id, ctx.workspace_id)
        if state is None:
            raise ApiError(404, "state_not_found", "Статус не найден")
        return state

    async def create(self, ctx: AccessContext, data: StateCreate) -> WorkflowState:
        if await self._states.name_taken(ctx.team, data.name):
            raise _name_taken(data.name)
        if data.is_default:
            await self._states.clear_default(ctx.team)
        position = data.position
        if position is None:
            position = await self._states.next_position(ctx.team)
        try:
            state = await self._states.add(
                WorkflowState(
                    workspace_id=ctx.workspace_id,
                    team_id=ctx.team,
                    name=data.name,
                    type=data.type,
                    color=data.color,
                    position=position,
                    is_default=data.is_default,
                )
            )
        except IntegrityError as error:
            await self._session.rollback()
            raise _name_taken(data.name) from error
        await self._session.commit()
        return state

    async def update(self, ctx: AccessContext, state_id: UUID, data: StateUpdate) -> WorkflowState:
        state = await self.get(ctx, state_id)
        changes = data.model_dump(exclude_unset=True)
        name = changes.get("name")
        if name is not None and await self._states.name_taken(
            state.team_id, name, exclude=state.id
        ):
            raise _name_taken(name)
        if changes.get("is_default") is False and state.is_default:
            raise _is_default()
        if changes.get("is_default") and not state.is_default:
            await self._states.clear_default(state.team_id)

        for field, value in changes.items():
            setattr(state, field, value)
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise _name_taken(str(name)) from error
        return state

    async def delete(self, ctx: AccessContext, state_id: UUID, move_to: UUID | None) -> None:
        # Импорт внутри: tasks зависит от states, и обратная связь на уровне модуля
        # замкнула бы импорт в кольцо.
        from app.modules.tasks.service import TaskService

        state = await self.get(ctx, state_id)
        if state.is_default:
            raise _is_default()
        tasks = TaskService(self._session)
        count = await tasks.count_in_state(state.id)
        if count:
            if move_to is None:
                raise ApiError(
                    409,
                    "state_has_tasks",
                    "В статусе есть задачи: укажите move_to — статус для их переноса",
                    {"task_count": count},
                )
            target = await self._states.get_in_team(move_to, state.team_id)
            if target is None or target.id == state.id:
                raise ApiError(
                    400,
                    "invalid_move_to",
                    "Переносить задачи можно только в другой статус той же команды",
                    {"move_to": str(move_to)},
                )
            await tasks.reassign_state(ctx, state, target)
        await self._states.delete(state.id, state.team_id)
        await self._session.commit()

    # --- Для других модулей -----------------------------------------------------

    async def default_for_team(self, team_id: UUID) -> WorkflowState:
        state = await self._states.default_for_team(team_id)
        # Инвариант: у каждой команды есть статус по умолчанию — его нельзя удалить
        # или снять, не назначив другой.
        assert state is not None, f"у команды {team_id} нет статуса по умолчанию"
        return state

    async def get_in_team(self, state_id: UUID, team_id: UUID) -> WorkflowState | None:
        return await self._states.get_in_team(state_id, team_id)

    async def get_many(self, state_ids: Sequence[UUID]) -> Sequence[WorkflowState]:
        return await self._states.get_many(state_ids)
