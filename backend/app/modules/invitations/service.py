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
from app.core.enums import (
    InvitationScope,
    InvitationStatus,
    LoginKind,
    ProjectRole,
    TeamRole,
    WorkspaceRole,
)
from app.core.errors import ApiError
from app.core.mail import MailMessage
from app.core.permissions import AccessContext, AccessTarget, Permission, resolve_access
from app.core.principal import WRITE, Principal
from app.core.security import generate_invitation_token, hash_token
from app.modules.auth.service import AuthService, SessionTokens
from app.modules.invitations.models import Invitation
from app.modules.invitations.repository import InvitationRepository
from app.modules.invitations.schemas import (
    InvitationAccept,
    InvitationCreate,
    InvitationPreview,
)
from app.modules.projects.service import ProjectService
from app.modules.teams.service import TeamService
from app.modules.users.models import User
from app.modules.users.schemas import RegisterRequest
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

    async def _ttl_days(self) -> int:
        from app.modules.instance.service import InstanceService

        return (await InstanceService(self._session).get()).invitation_ttl_days

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
                expires_at=now + timedelta(days=await self._ttl_days()),
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

    async def preview(self, raw_token: str) -> InvitationPreview:
        invitation = await self._invitations.get_by_hash(hash_token(raw_token))
        if invitation is None:
            raise _not_found()
        await self._expire_if_due(invitation)

        workspace = await self._workspaces.find(invitation.workspace_id)
        inviter = await self._users.find(invitation.invited_by)
        if workspace is None or inviter is None:
            raise _not_found()
        return InvitationPreview(
            workspace_name=workspace.name,
            inviter_name=inviter.full_name,
            email=invitation.email,
            scope_type=invitation.scope_type,
            role=invitation.role,
            status=invitation.status,
            expires_at=invitation.expires_at,
        )

    async def accept(
        self,
        raw_token: str,
        principal: Principal | None,
        data: InvitationAccept | None,
        *,
        user_agent: str | None,
        ip: str | None,
    ) -> tuple[Invitation, SessionTokens | None]:
        """Принять может только владелец адреса.

        Вошедший — если его email совпадает с приглашением; аноним — заведя
        учётную запись на этот адрес. Всё — одной транзакцией.
        """
        invitation = await self._invitations.get_by_hash(hash_token(raw_token), lock=True)
        if invitation is None:
            raise _not_found()
        await self._expire_if_due(invitation)
        if invitation.status != InvitationStatus.PENDING:
            raise _not_pending(invitation)
        if not await self._scope_exists(invitation):
            raise _not_found()

        tokens: SessionTokens | None = None
        if principal is not None:
            user = await self._signed_in_user(principal, invitation)
        else:
            user, tokens = await self._register(invitation, data, user_agent=user_agent, ip=ip)

        await self._grant(invitation, user.id)
        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = datetime.now(UTC)
        invitation.accepted_by = user.id
        await self._session.commit()
        return invitation, tokens

    async def _expire_if_due(self, invitation: Invitation) -> None:
        """Истечение помечается при обращении: фоновой чистки до этапа 9 нет."""
        if invitation.status == InvitationStatus.PENDING and invitation.expires_at <= datetime.now(
            UTC
        ):
            invitation.status = InvitationStatus.EXPIRED
            await self._session.commit()

    async def _scope_exists(self, invitation: Invitation) -> bool:
        match invitation.scope_type:
            case InvitationScope.TEAM:
                team = await self._teams.get_in_workspace(
                    invitation.scope_id, invitation.workspace_id
                )
                return team is not None
            case InvitationScope.PROJECT:
                project = await self._projects.get_in_workspace(
                    invitation.scope_id, invitation.workspace_id
                )
                return project is not None
            case _:
                # workspace держится внешним ключом: пропадёт он — пропадёт и приглашение.
                return True

    async def _signed_in_user(self, principal: Principal, invitation: Invitation) -> User:
        if WRITE not in principal.scopes:
            raise ApiError(403, "insufficient_scope", "Токен выдан только на чтение")
        user = await self._users.get_active(principal.user_id)
        # Пересланное письмо не должно давать доступ постороннему.
        if user.email.lower() != invitation.email.lower():
            raise ApiError(
                403,
                "invitation_email_mismatch",
                "Приглашение отправлено на другой адрес",
                {"email": invitation.email},
            )
        return user

    async def _register(
        self,
        invitation: Invitation,
        data: InvitationAccept | None,
        *,
        user_agent: str | None,
        ip: str | None,
    ) -> tuple[User, SessionTokens]:
        if data is None:
            raise ApiError(
                400,
                "registration_required",
                "Чтобы принять приглашение, войдите или укажите имя и пароль",
            )
        if await self._users.find_by_email(invitation.email) is not None:
            raise ApiError(
                409,
                "login_required",
                "Учётная запись с этим адресом уже есть — войдите, чтобы принять приглашение",
            )
        # Адрес берётся из приглашения, а не из тела: регистрируется ровно тот, кого звали.
        return await AuthService(self._session).create_account(
            RegisterRequest(
                email=invitation.email, password=data.password, full_name=data.full_name
            ),
            user_agent=user_agent,
            ip=ip,
            kind=LoginKind.INVITATION,
        )

    async def _grant(self, invitation: Invitation, user_id: UUID) -> None:
        workspace_id = invitation.workspace_id
        if invitation.scope_type == InvitationScope.WORKSPACE:
            await self._workspaces.grant(workspace_id, user_id, WorkspaceRole(invitation.role))
            return

        # Приглашение глубже workspace даёт гостевое членство в нём: без него
        # доступ к проекту висел бы в воздухе (и не прошёл бы составной FK).
        await self._workspaces.grant(workspace_id, user_id, WorkspaceRole.GUEST)
        if invitation.scope_type == InvitationScope.TEAM:
            await self._teams.grant(
                workspace_id, invitation.scope_id, user_id, TeamRole(invitation.role)
            )
        else:
            await self._projects.grant(
                workspace_id, invitation.scope_id, user_id, ProjectRole(invitation.role)
            )

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
