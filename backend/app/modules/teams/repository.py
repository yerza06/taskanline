"""Запросы к teams и team_members."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TeamRole
from app.modules.teams.models import Team, TeamMember
from app.modules.users.models import User


class TeamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_in_workspace(self, team_id: UUID, workspace_id: UUID) -> Team | None:
        team: Team | None = await self._session.scalar(
            select(Team).where(Team.id == team_id, Team.workspace_id == workspace_id)
        )
        return team

    async def key_taken(self, workspace_id: UUID, key: str, *, exclude: UUID | None = None) -> bool:
        condition = and_(Team.workspace_id == workspace_id, func.upper(Team.key) == key.upper())
        if exclude is not None:
            condition = and_(condition, Team.id != exclude)
        return bool(await self._session.scalar(select(exists().where(condition))))

    async def create(
        self, *, workspace_id: UUID, key: str, name: str, description: str | None, is_private: bool
    ) -> Team:
        team = Team(
            workspace_id=workspace_id,
            key=key,
            name=name,
            description=description,
            is_private=is_private,
        )
        self._session.add(team)
        await self._session.flush()
        return team

    async def list_visible(
        self, workspace_id: UUID, user_id: UUID, *, see_all: bool, see_public: bool
    ) -> Sequence[Team]:
        """Видимые команды: всем админам — все; участнику — открытые и свои; гостю — свои."""
        stmt = select(Team).where(Team.workspace_id == workspace_id).order_by(Team.key)
        if not see_all:
            is_member = exists().where(TeamMember.team_id == Team.id, TeamMember.user_id == user_id)
            stmt = stmt.where(
                or_(Team.is_private.is_(False), is_member) if see_public else is_member
            )
        return (await self._session.scalars(stmt)).all()

    async def delete(self, team_id: UUID, workspace_id: UUID) -> None:
        await self._session.execute(
            delete(Team).where(Team.id == team_id, Team.workspace_id == workspace_id)
        )

    async def get_member(self, team_id: UUID, user_id: UUID) -> TeamMember | None:
        member: TeamMember | None = await self._session.scalar(
            select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        )
        return member

    async def get_member_with_user(
        self, team_id: UUID, user_id: UUID
    ) -> tuple[TeamMember, User] | None:
        stmt = (
            select(TeamMember, User)
            .join(User, User.id == TeamMember.user_id)
            .where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        )
        return (await self._session.execute(stmt)).tuples().one_or_none()

    async def list_members(self, team_id: UUID) -> list[tuple[TeamMember, User]]:
        stmt = (
            select(TeamMember, User)
            .join(User, User.id == TeamMember.user_id)
            .where(TeamMember.team_id == team_id)
            .order_by(User.full_name, User.id)
        )
        return list((await self._session.execute(stmt)).tuples())

    async def add_member(
        self, *, workspace_id: UUID, team_id: UUID, user_id: UUID, role: TeamRole
    ) -> TeamMember:
        member = TeamMember(workspace_id=workspace_id, team_id=team_id, user_id=user_id, role=role)
        self._session.add(member)
        await self._session.flush()
        return member

    async def delete_member(self, member: TeamMember) -> None:
        await self._session.delete(member)
        await self._session.flush()

    async def memberships_of(self, user_id: UUID) -> Sequence[TeamMember]:
        stmt = (
            select(TeamMember).where(TeamMember.user_id == user_id).order_by(TeamMember.created_at)
        )
        return (await self._session.scalars(stmt)).all()
