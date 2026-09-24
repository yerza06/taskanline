"""HTTP-слой приглашений."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.mail import Mailer, get_mailer, send_safely
from app.core.principal import CurrentPrincipal, OptionalPrincipal, WritePrincipal
from app.core.rate_limit import rate_limit
from app.modules.auth.cookies import set_session_cookies
from app.modules.invitations.schemas import (
    InvitationAccept,
    InvitationAccepted,
    InvitationCreate,
    InvitationList,
    InvitationPreview,
    InvitationRead,
)
from app.modules.invitations.service import InvitationService

router = APIRouter(prefix="/invitations", tags=["invitations"])


def _invite_limit() -> tuple[int, int]:
    settings = get_settings()
    return settings.invite.attempts, settings.invite.window_seconds


def _accept_limit() -> tuple[int, int]:
    """Принятие без сессии — это регистрация, и перебор здесь стоит столько же."""
    settings = get_settings()
    return settings.auth.register_attempts, settings.auth.register_window_seconds


def get_invitation_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InvitationService:
    return InvitationService(session)


Service = Annotated[InvitationService, Depends(get_invitation_service)]


@router.post(
    "",
    response_model=InvitationRead,
    status_code=201,
    dependencies=[Depends(rate_limit("invite", _invite_limit))],
)
async def create_invitation(
    payload: InvitationCreate,
    principal: WritePrincipal,
    background: BackgroundTasks,
    mailer: Annotated[Mailer, Depends(get_mailer)],
    service: Service,
) -> InvitationRead:
    """Письмо уходит после ответа: сбой SMTP не отменяет созданного приглашения."""
    invitation, message = await service.create(principal, payload)
    background.add_task(send_safely, mailer, message)
    return InvitationRead.model_validate(invitation)


@router.get("", response_model=InvitationList)
async def list_invitations(
    workspace_id: Annotated[UUID, Query()], principal: CurrentPrincipal, service: Service
) -> InvitationList:
    invitations = await service.list_pending(principal, workspace_id)
    return InvitationList(items=[InvitationRead.model_validate(i) for i in invitations])


@router.delete("/{invitation_id}", status_code=204)
async def revoke_invitation(
    invitation_id: UUID, principal: WritePrincipal, service: Service
) -> None:
    await service.revoke(principal, invitation_id)


@router.get("/token/{token}", response_model=InvitationPreview)
async def preview_invitation(token: str, service: Service) -> InvitationPreview:
    """Без авторизации: по ссылке из письма приходит человек, которого в системе может не быть."""
    return await service.preview(token)


@router.post(
    "/token/{token}/accept",
    response_model=InvitationAccepted,
    dependencies=[Depends(rate_limit("invite_accept", _accept_limit))],
)
async def accept_invitation(
    token: str,
    request: Request,
    response: Response,
    principal: OptionalPrincipal,
    service: Service,
    payload: Annotated[InvitationAccept | None, Body()] = None,
) -> InvitationAccepted:
    invitation, tokens = await service.accept(
        token,
        principal,
        payload,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client is not None else None,
    )
    # Новая учётная запись сразу получает сессию — как после обычной регистрации.
    if tokens is not None:
        set_session_cookies(response, access=tokens.access, refresh=tokens.refresh)
    return InvitationAccepted(
        workspace_id=invitation.workspace_id,
        scope_type=invitation.scope_type,
        scope_id=invitation.scope_id,
        role=invitation.role,
    )
