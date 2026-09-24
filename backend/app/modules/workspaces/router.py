"""HTTP-слой рабочих пространств: права, вызов сервиса, сериализация."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.permissions import AccessContext, Permission, require_permission
from app.core.principal import CurrentPrincipal, WritePrincipal
from app.modules.users.models import User
from app.modules.workspaces.models import WorkspaceMember
from app.modules.workspaces.schemas import (
    OwnershipTransfer,
    WorkspaceCreate,
    WorkspaceList,
    WorkspaceMemberList,
    WorkspaceMemberRead,
    WorkspaceMemberUpdate,
    WorkspaceRead,
    WorkspaceUpdate,
    member_fields,
)
from app.modules.workspaces.service import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def get_workspace_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkspaceService:
    return WorkspaceService(session)


Service = Annotated[WorkspaceService, Depends(get_workspace_service)]


def _can(permission: Permission) -> Any:
    return Depends(require_permission(permission, on="workspace"))


CanRead = Annotated[AccessContext, _can(Permission.WORKSPACE_READ)]
CanUpdate = Annotated[AccessContext, _can(Permission.WORKSPACE_UPDATE)]
CanDelete = Annotated[AccessContext, _can(Permission.WORKSPACE_DELETE)]
CanTransfer = Annotated[AccessContext, _can(Permission.WORKSPACE_TRANSFER)]
CanSeeMembers = Annotated[AccessContext, _can(Permission.WORKSPACE_MEMBERS_READ)]
CanManageMembers = Annotated[AccessContext, _can(Permission.WORKSPACE_MEMBERS_MANAGE)]


def _member(member: WorkspaceMember, user: User) -> WorkspaceMemberRead:
    return WorkspaceMemberRead(**member_fields(user, member.created_at), role=member.role)


@router.get("", response_model=WorkspaceList)
async def list_workspaces(principal: CurrentPrincipal, service: Service) -> WorkspaceList:
    workspaces = await service.list_for(principal.user_id)
    return WorkspaceList(items=[WorkspaceRead.model_validate(w) for w in workspaces])


@router.post("", response_model=WorkspaceRead, status_code=201)
async def create_workspace(
    payload: WorkspaceCreate, principal: WritePrincipal, service: Service
) -> WorkspaceRead:
    return WorkspaceRead.model_validate(await service.create(principal.user_id, payload))


@router.get("/{workspace_id}", response_model=WorkspaceRead)
async def read_workspace(workspace_id: UUID, ctx: CanRead, service: Service) -> WorkspaceRead:
    return WorkspaceRead.model_validate(await service.get(ctx))


@router.patch("/{workspace_id}", response_model=WorkspaceRead)
async def update_workspace(
    workspace_id: UUID, payload: WorkspaceUpdate, ctx: CanUpdate, service: Service
) -> WorkspaceRead:
    return WorkspaceRead.model_validate(await service.update(ctx, payload))


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(workspace_id: UUID, ctx: CanDelete, service: Service) -> None:
    await service.delete(ctx)


@router.post("/{workspace_id}/transfer-ownership", status_code=204)
async def transfer_ownership(
    workspace_id: UUID, payload: OwnershipTransfer, ctx: CanTransfer, service: Service
) -> None:
    await service.transfer_ownership(ctx, payload.user_id)


@router.get("/{workspace_id}/members", response_model=WorkspaceMemberList)
async def list_members(
    workspace_id: UUID, ctx: CanSeeMembers, service: Service
) -> WorkspaceMemberList:
    members = await service.list_members(ctx)
    return WorkspaceMemberList(items=[_member(member, user) for member, user in members])


@router.patch("/{workspace_id}/members/{user_id}", response_model=WorkspaceMemberRead)
async def change_member_role(
    workspace_id: UUID,
    user_id: UUID,
    payload: WorkspaceMemberUpdate,
    ctx: CanManageMembers,
    service: Service,
) -> WorkspaceMemberRead:
    member, user = await service.change_member_role(ctx, user_id, payload.role)
    return _member(member, user)


@router.delete("/{workspace_id}/members/{user_id}", status_code=204)
async def remove_member(
    workspace_id: UUID, user_id: UUID, ctx: CanManageMembers, service: Service
) -> None:
    await service.remove_member(ctx, user_id)
