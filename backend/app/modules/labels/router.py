"""HTTP-слой меток."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.errors import ApiError
from app.core.permissions import (
    AccessContext,
    Permission,
    require_permission,
    resolve_access,
    resolve_team_read,
)
from app.core.principal import CurrentPrincipal
from app.modules.labels.schemas import LabelCreate, LabelList, LabelRead, LabelUpdate
from app.modules.labels.service import LabelService

router = APIRouter(prefix="/labels", tags=["labels"])

Session = Annotated[AsyncSession, Depends(get_session)]


def get_label_service(session: Session) -> LabelService:
    return LabelService(session)


Service = Annotated[LabelService, Depends(get_label_service)]


def _can(permission: Permission) -> Any:
    return Depends(require_permission(permission, on="label"))


CanManage = Annotated[AccessContext, _can(Permission.LABEL_MANAGE)]


def _team_not_found() -> ApiError:
    return ApiError(404, "team_not_found", "Команда не найдена")


@router.get("", response_model=LabelList)
async def list_labels(
    principal: CurrentPrincipal,
    session: Session,
    service: Service,
    workspace_id: Annotated[UUID, Query()],
    team_id: Annotated[UUID | None, Query()] = None,
) -> LabelList:
    if team_id is not None:
        ctx = await resolve_team_read(session, principal, team_id)
        if ctx.workspace_id != workspace_id:
            raise _team_not_found()
        labels = await service.list_for_team(ctx)
    else:
        ctx = await resolve_access(
            session,
            principal,
            on="workspace",
            object_id=workspace_id,
            permission=Permission.WORKSPACE_READ,
        )
        labels = await service.list_visible(ctx)
    return LabelList(items=[LabelRead.model_validate(label) for label in labels])


@router.post("", response_model=LabelRead, status_code=201)
async def create_label(
    payload: LabelCreate, principal: CurrentPrincipal, session: Session, service: Service
) -> LabelRead:
    if payload.team_id is not None:
        ctx = await resolve_access(
            session,
            principal,
            on="team",
            object_id=payload.team_id,
            permission=Permission.LABEL_MANAGE,
        )
        if ctx.workspace_id != payload.workspace_id:
            raise _team_not_found()
    else:
        ctx = await resolve_access(
            session,
            principal,
            on="workspace",
            object_id=payload.workspace_id,
            permission=Permission.LABEL_MANAGE,
        )
    return LabelRead.model_validate(await service.create(ctx, payload))


@router.patch("/{label_id}", response_model=LabelRead)
async def update_label(
    label_id: UUID, payload: LabelUpdate, ctx: CanManage, service: Service
) -> LabelRead:
    return LabelRead.model_validate(await service.update(ctx, label_id, payload))


@router.delete("/{label_id}", status_code=204)
async def delete_label(label_id: UUID, ctx: CanManage, service: Service) -> None:
    await service.delete(ctx, label_id)
