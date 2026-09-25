"""HTTP-слой проектов."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.permissions import AccessContext, AccessTarget, Permission, require_permission
from app.modules.projects.models import ProjectMember
from app.modules.projects.schemas import (
    ProjectCreate,
    ProjectList,
    ProjectMemberList,
    ProjectMemberRead,
    ProjectMemberUpdate,
    ProjectRead,
    ProjectUpdate,
)
from app.modules.projects.service import ProjectService
from app.modules.users.models import User
from app.modules.workspaces.schemas import member_fields

team_projects_router = APIRouter(prefix="/teams/{team_id}/projects", tags=["projects"])
router = APIRouter(prefix="/projects", tags=["projects"])


def get_project_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProjectService:
    return ProjectService(session)


Service = Annotated[ProjectService, Depends(get_project_service)]


def _can(permission: Permission, on: AccessTarget = "project") -> Any:
    return Depends(require_permission(permission, on=on))


CanList = Annotated[AccessContext, _can(Permission.TEAM_READ, "team")]
CanCreate = Annotated[AccessContext, _can(Permission.PROJECT_CREATE, "team")]
CanRead = Annotated[AccessContext, _can(Permission.PROJECT_READ)]
CanUpdate = Annotated[AccessContext, _can(Permission.PROJECT_UPDATE)]
CanArchive = Annotated[AccessContext, _can(Permission.PROJECT_ARCHIVE)]
CanDelete = Annotated[AccessContext, _can(Permission.PROJECT_DELETE)]
CanManageMembers = Annotated[AccessContext, _can(Permission.PROJECT_MEMBERS_MANAGE)]


def _member(member: ProjectMember, user: User) -> ProjectMemberRead:
    return ProjectMemberRead(**member_fields(user, member.created_at), role=member.role)


@team_projects_router.get("", response_model=ProjectList)
async def list_projects(
    team_id: UUID,
    ctx: CanList,
    service: Service,
    include_archived: Annotated[bool, Query()] = False,
) -> ProjectList:
    projects = await service.list_for_team(ctx, include_archived=include_archived)
    return ProjectList(items=[ProjectRead.model_validate(p) for p in projects])


@team_projects_router.post("", response_model=ProjectRead, status_code=201)
async def create_project(
    team_id: UUID, payload: ProjectCreate, ctx: CanCreate, service: Service
) -> ProjectRead:
    return ProjectRead.model_validate(await service.create(ctx, payload))


@router.get("/{project_id}", response_model=ProjectRead)
async def read_project(project_id: UUID, ctx: CanRead, service: Service) -> ProjectRead:
    return ProjectRead.model_validate(await service.get(ctx))


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: UUID, payload: ProjectUpdate, ctx: CanUpdate, service: Service
) -> ProjectRead:
    return ProjectRead.model_validate(await service.update(ctx, payload))


@router.post("/{project_id}/archive", response_model=ProjectRead)
async def archive_project(project_id: UUID, ctx: CanArchive, service: Service) -> ProjectRead:
    return ProjectRead.model_validate(await service.archive(ctx))


@router.post("/{project_id}/unarchive", response_model=ProjectRead)
async def unarchive_project(project_id: UUID, ctx: CanArchive, service: Service) -> ProjectRead:
    return ProjectRead.model_validate(await service.unarchive(ctx))


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: UUID, ctx: CanDelete, service: Service) -> None:
    await service.delete(ctx)


@router.get("/{project_id}/members", response_model=ProjectMemberList)
async def list_members(project_id: UUID, ctx: CanRead, service: Service) -> ProjectMemberList:
    members = await service.list_members(ctx)
    return ProjectMemberList(items=[_member(member, user) for member, user in members])


@router.patch("/{project_id}/members/{user_id}", response_model=ProjectMemberRead)
async def change_member_role(
    project_id: UUID,
    user_id: UUID,
    payload: ProjectMemberUpdate,
    ctx: CanManageMembers,
    service: Service,
) -> ProjectMemberRead:
    member, user = await service.change_member_role(ctx, user_id, payload.role)
    return _member(member, user)


@router.delete("/{project_id}/members/{user_id}", status_code=204)
async def remove_member(
    project_id: UUID, user_id: UUID, ctx: CanManageMembers, service: Service
) -> None:
    await service.remove_member(ctx, user_id)
