"""HTTP-слой workflow-статусов."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.permissions import (
    AccessContext,
    AccessTarget,
    Permission,
    require_permission,
    require_team_read,
)
from app.modules.states.schemas import StateCreate, StateList, StateRead, StateUpdate
from app.modules.states.service import StateService

team_states_router = APIRouter(prefix="/teams/{team_id}/states", tags=["states"])
router = APIRouter(prefix="/states", tags=["states"])


def get_state_service(session: Annotated[AsyncSession, Depends(get_session)]) -> StateService:
    return StateService(session)


Service = Annotated[StateService, Depends(get_state_service)]


def _can(permission: Permission, on: AccessTarget) -> Any:
    return Depends(require_permission(permission, on=on))


CanList = Annotated[AccessContext, Depends(require_team_read)]
CanCreate = Annotated[AccessContext, _can(Permission.STATE_MANAGE, "team")]
CanManage = Annotated[AccessContext, _can(Permission.STATE_MANAGE, "state")]


@team_states_router.get("", response_model=StateList)
async def list_states(team_id: UUID, ctx: CanList, service: Service) -> StateList:
    return StateList(items=[StateRead.model_validate(s) for s in await service.list_for_team(ctx)])


@team_states_router.post("", response_model=StateRead, status_code=201)
async def create_state(
    team_id: UUID, payload: StateCreate, ctx: CanCreate, service: Service
) -> StateRead:
    return StateRead.model_validate(await service.create(ctx, payload))


@router.patch("/{state_id}", response_model=StateRead)
async def update_state(
    state_id: UUID, payload: StateUpdate, ctx: CanManage, service: Service
) -> StateRead:
    return StateRead.model_validate(await service.update(ctx, state_id, payload))


@router.delete("/{state_id}", status_code=204)
async def delete_state(
    state_id: UUID,
    ctx: CanManage,
    service: Service,
    move_to: Annotated[UUID | None, Query(description="Статус для переноса задач")] = None,
) -> None:
    await service.delete(ctx, state_id, move_to)
