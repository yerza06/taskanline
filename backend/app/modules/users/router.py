"""Профиль текущего пользователя."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.principal import CurrentPrincipal, Principal, WritePrincipal
from app.modules.users.models import User
from app.modules.users.schemas import MeResponse, UserUpdate
from app.modules.users.service import UserService

router = APIRouter(prefix="/me", tags=["me"])


def get_user_service(session: Annotated[AsyncSession, Depends(get_session)]) -> UserService:
    return UserService(session)


def _me(user: User, principal: Principal) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        role=user.role,
        created_at=user.created_at,
        auth_method=principal.auth_method,
        scopes=sorted(principal.scopes),
    )


@router.get("", response_model=MeResponse)
async def read_me(
    principal: CurrentPrincipal,
    service: Annotated[UserService, Depends(get_user_service)],
) -> MeResponse:
    return _me(await service.get_active(principal.user_id), principal)


@router.patch("", response_model=MeResponse)
async def update_me(
    payload: UserUpdate,
    principal: WritePrincipal,
    service: Annotated[UserService, Depends(get_user_service)],
) -> MeResponse:
    return _me(await service.update_profile(principal.user_id, payload), principal)
