"""Профиль текущего пользователя."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.principal import CurrentPrincipal, Principal, WritePrincipal
from app.modules.projects.service import ProjectService
from app.modules.teams.service import TeamService
from app.modules.users.models import User
from app.modules.users.schemas import (
    Memberships,
    MeResponse,
    ProjectMembership,
    TeamMembership,
    UserUpdate,
    WorkspaceMembership,
)
from app.modules.users.service import UserService
from app.modules.workspaces.service import WorkspaceService

router = APIRouter(prefix="/me", tags=["me"])


def get_user_service(session: Annotated[AsyncSession, Depends(get_session)]) -> UserService:
    return UserService(session)


async def get_memberships(
    principal: CurrentPrincipal, session: Annotated[AsyncSession, Depends(get_session)]
) -> Memberships:
    """Сводка из трёх модулей: каждый отвечает за свою таблицу членства."""
    user_id = principal.user_id
    workspaces = await WorkspaceService(session).memberships_of(user_id)
    teams = await TeamService(session).memberships_of(user_id)
    projects = await ProjectService(session).memberships_of(user_id)
    return Memberships(
        workspaces=[
            WorkspaceMembership(workspace_id=m.workspace_id, role=m.role) for m in workspaces
        ],
        teams=[
            TeamMembership(team_id=m.team_id, workspace_id=m.workspace_id, role=m.role)
            for m in teams
        ],
        projects=[
            ProjectMembership(project_id=m.project_id, workspace_id=m.workspace_id, role=m.role)
            for m in projects
        ],
    )


CurrentMemberships = Annotated[Memberships, Depends(get_memberships)]


def _me(user: User, principal: Principal, memberships: Memberships) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        role=user.role,
        created_at=user.created_at,
        auth_method=principal.auth_method,
        scopes=sorted(principal.scopes),
        memberships=memberships,
    )


@router.get("", response_model=MeResponse)
async def read_me(
    principal: CurrentPrincipal,
    service: Annotated[UserService, Depends(get_user_service)],
    memberships: CurrentMemberships,
) -> MeResponse:
    return _me(await service.get_active(principal.user_id), principal, memberships)


@router.patch("", response_model=MeResponse)
async def update_me(
    payload: UserUpdate,
    principal: WritePrincipal,
    service: Annotated[UserService, Depends(get_user_service)],
    memberships: CurrentMemberships,
) -> MeResponse:
    return _me(await service.update_profile(principal.user_id, payload), principal, memberships)
