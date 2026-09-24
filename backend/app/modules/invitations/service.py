"""Приглашения: создание с письмом, список, отзыв; превью и принятие — по токену.

Сервис стоит поверх workspaces, teams и projects: членства создаёт их сервисами,
никогда не их репозиториями.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import InvitationScope, InvitationStatus
from app.core.errors import ApiError
from app.core.mail import MailMessage
from app.core.permissions import AccessContext, AccessTarget, Permission, resolve_access
from app.core.principal import Principal
from app.core.security import generate_invitation_token, hash_token
from app.modules.invitations.models import Invitation
from app.modules.invitations.repository import InvitationRepository
from app.modules.invitations.schemas import InvitationCreate
from app.modules.projects.service import ProjectService
from app.modules.teams.service import TeamService
from app.modules.users.service import UserService
from app.modules.workspaces.service import WorkspaceService

_TARGET: dict[InvitationScope, AccessTarget] = {
    InvitationScope.WORKSPACE: "workspace",
    InvitationScope.TEAM: "team",
    InvitationScope.PROJECT: "project",
}
_INVITE: dict[InvitationScope, Permission] = {
    InvitationScope.WORKSPACE: Permission.WORKSPACE_INVITE,
    InvitationScope.TEAM: Permission.TEAM_INVITE,
    InvitationScope.PROJECT: Permission.PROJECT_INVITE,
}


def _not_found() -> ApiError:
    return ApiError(404, "invitation_not_found", "Приглашение не найдено")


def _not_pending(invitation: Invitation) -> ApiError:
    return ApiError(
        409,
        "invitation_not_pending",
        "Приглашение уже недействительно",
        {"status": str(invitation.status)},
    )


def _invitation_exists() -> ApiError:
    return ApiError(409, "invitation_exists", "Приглашение на этот адрес уже отправлено")


class InvitationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._invitations = InvitationRepository(session)
        self._users = UserService(session)
        self._workspaces = WorkspaceService(session)
        self._teams = TeamService(session)
        self._projects = ProjectService(session)

    async def create(
        self, principal: Principal, data: InvitationCreate
    ) -> tuple[Invitation, MailMessage]:
        """Запись и письмо к ней. Письмо отправляет вызывающий — в фоне, после ответа."""
        ctx = await self._access(principal, data.scope_type, data.scope_id)
        invitee = await self._users.find_by_email(data.email)
        if invitee is not None and await self._is_member(ctx, data.scope_type, invitee.id):
            raise ApiError(
                409, "already_member", "Этот человек уже участник", {"email": data.email}
            )

        now = datetime.now(UTC)
        previous = await self._invitations.find_pending(
            ctx.workspace_id, data.email, data.scope_type, data.scope_id
        )
        if previous is not None:
            if previous.expires_at > now:
                raise _invitation_exists()
            # Просроченное, но не помеченное держало бы уникальный индекс вечно.
            previous.status = InvitationStatus.EXPIRED
            await self._session.flush()

        raw = generate_invitation_token()
        try:
            invitation = await self._invitations.create(
                workspace_id=ctx.workspace_id,
                email=data.email,
                scope_type=data.scope_type,
                scope_id=data.scope_id,
                role=data.role,
                token_hash=hash_token(raw),
                invited_by=principal.user_id,
                expires_at=now + timedelta(days=get_settings().invite.ttl_days),
            )
        except IntegrityError as error:
            await self._session.rollback()
            raise _invitation_exists() from error

        message = await self._message(invitation, raw)
        await self._session.commit()
        return invitation, message

    async def list_pending(self, principal: Principal, workspace_id: UUID) -> Sequence[Invitation]:
        ctx = await resolve_access(
            self._session,
            principal,
            on="workspace",
            object_id=workspace_id,
            permission=Permission.WORKSPACE_INVITATIONS_READ,
        )
        return await self._invitations.list_pending(ctx.workspace_id, datetime.now(UTC))

    async def revoke(self, principal: Principal, invitation_id: UUID) -> None:
        invitation = await self._invitations.get(invitation_id)
        if invitation is None:
            raise _not_found()
        try:
            await self._access(principal, invitation.scope_type, invitation.scope_id)
        except ApiError as error:
            # Объект не виден — не видно и приглашения в него.
            if error.status_code == 404:
                raise _not_found() from error
            raise
        if invitation.status != InvitationStatus.PENDING:
            raise _not_pending(invitation)

        invitation.status = InvitationStatus.REVOKED
        await self._session.commit()

    async def revoke_for_team(self, workspace_id: UUID, team_id: UUID) -> None:
        """Без commit: вызывается из удаления команды, в его транзакции."""
        await self._invitations.revoke_for_team(workspace_id, team_id)

    async def revoke_for_project(self, workspace_id: UUID, project_id: UUID) -> None:
        await self._invitations.revoke_for_project(workspace_id, project_id)

    async def _access(
        self, principal: Principal, scope_type: InvitationScope, scope_id: UUID
    ) -> AccessContext:
        return await resolve_access(
            self._session,
            principal,
            on=_TARGET[InvitationScope(scope_type)],
            object_id=scope_id,
            permission=_INVITE[InvitationScope(scope_type)],
        )

    async def _is_member(
        self, ctx: AccessContext, scope_type: InvitationScope, user_id: UUID
    ) -> bool:
        role: object = None
        match scope_type:
            case InvitationScope.WORKSPACE:
                role = await self._workspaces.get_member_role(ctx.workspace_id, user_id)
            case InvitationScope.TEAM:
                role = await self._teams.get_member_role(ctx.team, user_id)
            case InvitationScope.PROJECT:
                role = await self._projects.get_member_role(ctx.project, user_id)
        return role is not None

    async def _message(self, invitation: Invitation, raw_token: str) -> MailMessage:
        workspace = await self._workspaces.find(invitation.workspace_id)
        inviter = await self._users.find(invitation.invited_by)
        workspace_name = workspace.name if workspace is not None else "TasKanLine"
        inviter_name = inviter.full_name if inviter is not None else "Коллега"
        link = f"{get_settings().app.public_url.rstrip('/')}/invite/{raw_token}"
        return MailMessage(
            to=invitation.email,
            subject=f"Приглашение в «{workspace_name}»",
            body=(
                f"{inviter_name} приглашает вас в рабочее пространство «{workspace_name}» "
                f"в TasKanLine.\n\n"
                f"Принять приглашение: {link}\n\n"
                f"Ссылка действует до {invitation.expires_at:%d.%m.%Y}. "
                f"Если вы не ждали этого письма, просто удалите его."
            ),
        )
