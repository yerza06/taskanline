"""HTTP-слой приглашений."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.mail import Mailer, get_mailer, send_safely
from app.core.principal import CurrentPrincipal, WritePrincipal
from app.core.rate_limit import rate_limit
from app.modules.invitations.schemas import InvitationCreate, InvitationList, InvitationRead
from app.modules.invitations.service import InvitationService

router = APIRouter(prefix="/invitations", tags=["invitations"])


def _invite_limit() -> tuple[int, int]:
    settings = get_settings()
    return settings.invite.attempts, settings.invite.window_seconds


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
