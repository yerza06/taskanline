"""HTTP-слой команд."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.permissions import AccessContext, AccessTarget, Permission, require_permission
from app.modules.teams.models import TeamMember
from app.modules.teams.schemas import (
    TeamCreate,
    TeamList,
    TeamMemberList,
    TeamMemberRead,
    TeamMemberUpdate,
    TeamRead,
    TeamUpdate,
)
from app.modules.teams.service import TeamService
from app.modules.users.models import User
from app.modules.workspaces.schemas import member_fields

# Команды создаются и перечисляются внутри workspace, живут — по своему адресу.
workspace_teams_router = APIRouter(prefix="/workspaces/{workspace_id}/teams", tags=["teams"])
router = APIRouter(prefix="/teams", tags=["teams"])


def get_team_service(session: Annotated[AsyncSession, Depends(get_session)]) -> TeamService:
    return TeamService(session)


Service = Annotated[TeamService, Depends(get_team_service)]


def _can(permission: Permission, on: AccessTarget = "team") -> Any:
    return Depends(require_permission(permission, on=on))


CanList = Annotated[AccessContext, _can(Permission.WORKSPACE_READ, "workspace")]
CanCreate = Annotated[AccessContext, _can(Permission.TEAM_CREATE, "workspace")]
CanRead = Annotated[AccessContext, _can(Permission.TEAM_READ)]
CanUpdate = Annotated[AccessContext, _can(Permission.TEAM_UPDATE)]
CanDelete = Annotated[AccessContext, _can(Permission.TEAM_DELETE)]
CanManageMembers = Annotated[AccessContext, _can(Permission.TEAM_MEMBERS_MANAGE)]


def _member(member: TeamMember, user: User) -> TeamMemberRead:
    return TeamMemberRead(**member_fields(user, member.created_at), role=member.role)


@workspace_teams_router.get("", response_model=TeamList)
async def list_teams(workspace_id: UUID, ctx: CanList, service: Service) -> TeamList:
    return TeamList(items=[TeamRead.model_validate(t) for t in await service.list_visible(ctx)])


@workspace_teams_router.post("", response_model=TeamRead, status_code=201)
async def create_team(
    workspace_id: UUID, payload: TeamCreate, ctx: CanCreate, service: Service
) -> TeamRead:
    return TeamRead.model_validate(await service.create(ctx, payload))


@router.get("/{team_id}", response_model=TeamRead)
async def read_team(team_id: UUID, ctx: CanRead, service: Service) -> TeamRead:
    return TeamRead.model_validate(await service.get(ctx))


@router.patch("/{team_id}", response_model=TeamRead)
async def update_team(
    team_id: UUID, payload: TeamUpdate, ctx: CanUpdate, service: Service
) -> TeamRead:
    return TeamRead.model_validate(await service.update(ctx, payload))


@router.delete("/{team_id}", status_code=204)
async def delete_team(team_id: UUID, ctx: CanDelete, service: Service) -> None:
    await service.delete(ctx)


@router.get("/{team_id}/members", response_model=TeamMemberList)
async def list_members(team_id: UUID, ctx: CanRead, service: Service) -> TeamMemberList:
    members = await service.list_members(ctx)
    return TeamMemberList(items=[_member(member, user) for member, user in members])


@router.patch("/{team_id}/members/{user_id}", response_model=TeamMemberRead)
async def change_member_role(
    team_id: UUID, user_id: UUID, payload: TeamMemberUpdate, ctx: CanManageMembers, service: Service
) -> TeamMemberRead:
    member, user = await service.change_member_role(ctx, user_id, payload.role)
    return _member(member, user)


@router.delete("/{team_id}/members/{user_id}", status_code=204)
async def remove_member(
    team_id: UUID, user_id: UUID, ctx: CanManageMembers, service: Service
) -> None:
    await service.remove_member(ctx, user_id)
