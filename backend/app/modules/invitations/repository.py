"""Запросы к invitations."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InvitationScope, InvitationStatus
from app.modules.invitations.models import Invitation
from app.modules.projects.models import Project


class InvitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        workspace_id: UUID,
        email: str,
        scope_type: InvitationScope,
        scope_id: UUID,
        role: str,
        token_hash: str,
        invited_by: UUID,
        expires_at: datetime,
    ) -> Invitation:
        invitation = Invitation(
            workspace_id=workspace_id,
            email=email,
            scope_type=scope_type,
            scope_id=scope_id,
            role=role,
            token_hash=token_hash,
            invited_by=invited_by,
            expires_at=expires_at,
        )
        self._session.add(invitation)
        await self._session.flush()
        return invitation

    async def get(self, invitation_id: UUID) -> Invitation | None:
        return await self._session.get(Invitation, invitation_id)

    async def get_by_hash(self, token_hash: str, *, lock: bool = False) -> Invitation | None:
        """`lock` — для принятия: два одновременных клика не создают членство дважды."""
        stmt = select(Invitation).where(Invitation.token_hash == token_hash)
        if lock:
            stmt = stmt.with_for_update()
        invitation: Invitation | None = await self._session.scalar(stmt)
        return invitation

    async def find_pending(
        self, workspace_id: UUID, email: str, scope_type: InvitationScope, scope_id: UUID
    ) -> Invitation | None:
        invitation: Invitation | None = await self._session.scalar(
            select(Invitation).where(
                Invitation.workspace_id == workspace_id,
                Invitation.email == email,
                Invitation.scope_type == scope_type,
                Invitation.scope_id == scope_id,
                Invitation.status == InvitationStatus.PENDING,
            )
        )
        return invitation

    async def list_pending(self, workspace_id: UUID, now: datetime) -> Sequence[Invitation]:
        stmt = (
            select(Invitation)
            .where(
                Invitation.workspace_id == workspace_id,
                Invitation.status == InvitationStatus.PENDING,
                Invitation.expires_at > now,
            )
            .order_by(Invitation.created_at.desc(), Invitation.id)
        )
        return (await self._session.scalars(stmt)).all()

    async def revoke_for_team(self, workspace_id: UUID, team_id: UUID) -> None:
        """Приглашения в команду и во все её проекты — до удаления самих проектов."""
        team_projects = select(Project.id).where(
            Project.workspace_id == workspace_id, Project.team_id == team_id
        )
        await self._revoke_where(
            workspace_id,
            or_(
                and_(Invitation.scope_type == InvitationScope.TEAM, Invitation.scope_id == team_id),
                and_(
                    Invitation.scope_type == InvitationScope.PROJECT,
                    Invitation.scope_id.in_(team_projects),
                ),
            ),
        )

    async def revoke_for_project(self, workspace_id: UUID, project_id: UUID) -> None:
        await self._revoke_where(
            workspace_id,
            and_(
                Invitation.scope_type == InvitationScope.PROJECT,
                Invitation.scope_id == project_id,
            ),
        )

    async def _revoke_where(self, workspace_id: UUID, condition: object) -> None:
        await self._session.execute(
            update(Invitation)
            .where(
                Invitation.workspace_id == workspace_id,
                Invitation.status == InvitationStatus.PENDING,
                condition,  # type: ignore[arg-type]
            )
            .values(status=InvitationStatus.REVOKED)
            .execution_options(synchronize_session=False)
        )
