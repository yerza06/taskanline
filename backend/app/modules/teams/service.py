"""Бизнес-правила команд и участия в них."""

from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TeamRole
from app.core.errors import ApiError
from app.core.permissions import AccessContext, EffectiveRole
from app.modules.states.service import StateService
from app.modules.teams.models import Team, TeamMember
from app.modules.teams.repository import TeamRepository
from app.modules.teams.schemas import TeamCreate, TeamUpdate
from app.modules.users.models import User

ROLE_RANK = {TeamRole.MEMBER: 0, TeamRole.LEAD: 1}

Member = tuple[TeamMember, User]


def _key_taken(key: str) -> ApiError:
    return ApiError(409, "team_key_taken", "Команда с таким ключом уже есть", {"key": key})


def _team_not_found() -> ApiError:
    return ApiError(404, "team_not_found", "Команда не найдена")


class TeamService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._teams = TeamRepository(session)

    async def create(self, ctx: AccessContext, data: TeamCreate) -> Team:
        if await self._teams.key_taken(ctx.workspace_id, data.key):
            raise _key_taken(data.key)
        try:
            team = await self._teams.create(
                workspace_id=ctx.workspace_id,
                key=data.key,
                name=data.name,
                description=data.description,
                is_private=data.is_private,
            )
            # Создатель ведёт команду: приватная команда без единого участника
            # была бы невидима всем, кроме администраторов.
            await self._teams.add_member(
                workspace_id=ctx.workspace_id,
                team_id=team.id,
                user_id=ctx.principal.user_id,
                role=TeamRole.LEAD,
            )
            await StateService(self._session).create_defaults(ctx.workspace_id, team.id)
        except IntegrityError as error:
            await self._session.rollback()
            raise _key_taken(data.key) from error
        await self._session.commit()
        return team

    async def list_visible(self, ctx: AccessContext) -> Sequence[Team]:
        return await self._teams.list_visible(
            ctx.workspace_id,
            ctx.principal.user_id,
            see_all=ctx.role >= EffectiveRole.ADMIN,
            see_public=ctx.role >= EffectiveRole.MEMBER,
        )

    async def get(self, ctx: AccessContext) -> Team:
        team = await self._teams.get_in_workspace(ctx.team, ctx.workspace_id)
        if team is None:
            raise _team_not_found()
        return team

    async def get_in_workspace(self, team_id: UUID, workspace_id: UUID) -> Team | None:
        return await self._teams.get_in_workspace(team_id, workspace_id)

    async def get_many(self, team_ids: Sequence[UUID], workspace_id: UUID) -> Sequence[Team]:
        return await self._teams.get_many(team_ids, workspace_id)

    async def next_task_number(self, team_id: UUID) -> int:
        return await self._teams.next_task_number(team_id)

    async def lock(self, team_id: UUID) -> None:
        await self._teams.lock(team_id)

    async def update(self, ctx: AccessContext, data: TeamUpdate) -> Team:
        team = await self.get(ctx)
        changes = data.model_dump(exclude_unset=True)
        key = changes.get("key")
        if key is not None and key != team.key:
            if ctx.role < EffectiveRole.OWNER:
                raise ApiError(
                    403,
                    "insufficient_role",
                    "Ключ команды меняет только владелец: он входит в идентификаторы задач",
                    {"required": "owner"},
                )
            if await self._teams.key_taken(ctx.workspace_id, key, exclude=team.id):
                raise _key_taken(key)

        for field, value in changes.items():
            setattr(team, field, value)
        if changes:
            team.updated_at = datetime.now(UTC)
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise _key_taken(str(key)) from error
        return team

    async def delete(self, ctx: AccessContext) -> None:
        # Импорт внутри: invitations стоит поверх teams, и обратная связь на уровне
        # модуля замкнула бы импорт в кольцо.
        from app.modules.invitations.service import InvitationService

        # Проекты команды ещё на месте: отзыв находит приглашения и в них.
        await InvitationService(self._session).revoke_for_team(ctx.workspace_id, ctx.team)
        await self._teams.delete(ctx.team, ctx.workspace_id)
        await self._session.commit()

    async def list_members(self, ctx: AccessContext) -> list[Member]:
        return await self._teams.list_members(ctx.team)

    async def change_member_role(self, ctx: AccessContext, user_id: UUID, role: TeamRole) -> Member:
        member, user = await self._member(ctx.team, user_id)
        member.role = role
        await self._session.commit()
        return member, user

    async def remove_member(self, ctx: AccessContext, user_id: UUID) -> None:
        member, _ = await self._member(ctx.team, user_id)
        await self._teams.delete_member(member)
        await self._session.commit()

    async def grant(self, workspace_id: UUID, team_id: UUID, user_id: UUID, role: TeamRole) -> None:
        """Членство по приглашению: создать или повысить. Без commit.

        Вставка — `INSERT ... ON CONFLICT DO NOTHING`: конкурентный accept того же
        членства не должен ронять транзакцию в `IntegrityError`.
        """
        member = await self._teams.add_member_if_absent(
            workspace_id=workspace_id, team_id=team_id, user_id=user_id, role=role
        )
        if ROLE_RANK[role] > ROLE_RANK[TeamRole(member.role)]:
            member.role = role
            await self._session.flush()

    async def get_member_role(self, team_id: UUID, user_id: UUID) -> TeamRole | None:
        member = await self._teams.get_member(team_id, user_id)
        return TeamRole(member.role) if member is not None else None

    async def memberships_of(self, user_id: UUID) -> Sequence[TeamMember]:
        return await self._teams.memberships_of(user_id)

    async def _member(self, team_id: UUID, user_id: UUID) -> Member:
        found = await self._teams.get_member_with_user(team_id, user_id)
        if found is None:
            raise ApiError(404, "member_not_found", "Участник не найден")
        return found

    # --- Для админ-панели ---------------------------------------------------------

    async def counts_by_workspace(self, ids: Collection[UUID]) -> dict[UUID, int]:
        return await self._teams.counts_by_workspace(ids)

    async def count(self) -> int:
        return await self._teams.count()
