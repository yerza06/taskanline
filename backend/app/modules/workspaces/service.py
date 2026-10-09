"""Бизнес-правила рабочих пространств и участия в них."""

from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import WorkspaceRole
from app.core.errors import ApiError
from app.core.permissions import AccessContext, EffectiveRole
from app.modules.users.models import User
from app.modules.workspaces.models import Workspace, WorkspaceMember
from app.modules.workspaces.repository import WorkspaceRepository
from app.modules.workspaces.schemas import WorkspaceCreate, WorkspaceUpdate

# Порядок для «повысить, но не понизить» при принятии приглашения.
ROLE_RANK = {
    WorkspaceRole.GUEST: 0,
    WorkspaceRole.MEMBER: 1,
    WorkspaceRole.ADMIN: 2,
    WorkspaceRole.OWNER: 3,
}

Member = tuple[WorkspaceMember, User]


def _slug_taken(slug: str) -> ApiError:
    return ApiError(
        409, "workspace_slug_taken", "Этот адрес рабочего пространства уже занят", {"slug": slug}
    )


def _member_not_found() -> ApiError:
    return ApiError(404, "member_not_found", "Участник не найден")


class WorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._workspaces = WorkspaceRepository(session)

    async def create(self, user_id: UUID, data: WorkspaceCreate) -> Workspace:
        if await self._workspaces.slug_taken(data.slug):
            raise _slug_taken(data.slug)
        try:
            workspace = await self._workspaces.create(
                name=data.name, slug=data.slug, created_by=user_id
            )
            # Создатель — владелец: иначе пространством с первой секунды некому управлять.
            await self._workspaces.add_member(
                workspace_id=workspace.id, user_id=user_id, role=WorkspaceRole.OWNER
            )
        except IntegrityError as error:
            # Проверка выше не спасает от гонки двух одновременных созданий.
            await self._session.rollback()
            raise _slug_taken(data.slug) from error
        await self._session.commit()
        return workspace

    async def list_for(self, user_id: UUID) -> Sequence[Workspace]:
        return await self._workspaces.list_for_user(user_id)

    async def get(self, ctx: AccessContext) -> Workspace:
        workspace = await self._workspaces.get(ctx.workspace_id)
        if workspace is None:
            raise ApiError(404, "workspace_not_found", "Рабочее пространство не найдено")
        return workspace

    async def find(self, workspace_id: UUID) -> Workspace | None:
        """Без проверки прав — для внутренних нужд вроде превью приглашения."""
        return await self._workspaces.get(workspace_id)

    async def update(self, ctx: AccessContext, data: WorkspaceUpdate) -> Workspace:
        workspace = await self.get(ctx)
        changes = data.model_dump(exclude_unset=True)
        slug = changes.get("slug")
        if slug is not None and await self._workspaces.slug_taken(slug, exclude=workspace.id):
            raise _slug_taken(slug)

        for field, value in changes.items():
            setattr(workspace, field, value)
        if changes:
            workspace.updated_at = datetime.now(UTC)
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise _slug_taken(str(slug)) from error
        return workspace

    async def delete(self, ctx: AccessContext) -> None:
        await self._workspaces.delete(ctx.workspace_id)
        await self._session.commit()

    async def list_members(self, ctx: AccessContext) -> list[Member]:
        return await self._workspaces.list_members(ctx.workspace_id)

    async def change_member_role(
        self, ctx: AccessContext, user_id: UUID, role: WorkspaceRole
    ) -> Member:
        member, user = await self._member(ctx.workspace_id, user_id)
        self._guard_owner(ctx, WorkspaceRole(member.role), role)
        if member.role == WorkspaceRole.OWNER and role != WorkspaceRole.OWNER:
            await self._ensure_other_owner(ctx.workspace_id)

        member.role = role
        await self._session.commit()
        return member, user

    async def remove_member(self, ctx: AccessContext, user_id: UUID) -> None:
        member, _ = await self._member(ctx.workspace_id, user_id)
        self._guard_owner(ctx, WorkspaceRole(member.role))
        if member.role == WorkspaceRole.OWNER:
            await self._ensure_other_owner(ctx.workspace_id)

        await self._workspaces.delete_member(member)
        await self._session.commit()

    async def transfer_ownership(self, ctx: AccessContext, user_id: UUID) -> None:
        """Получатель становится владельцем, передающий — администратором."""
        if user_id == ctx.principal.user_id:
            raise ApiError(400, "invalid_transfer", "Нельзя передать владение самому себе")

        target, _ = await self._member(ctx.workspace_id, user_id)
        current = await self._workspaces.get_member(ctx.workspace_id, ctx.principal.user_id)
        if current is None:
            raise _member_not_found()

        target.role = WorkspaceRole.OWNER
        current.role = WorkspaceRole.ADMIN
        await self._session.commit()

    async def grant(self, workspace_id: UUID, user_id: UUID, role: WorkspaceRole) -> None:
        """Членство по принятому приглашению: создать или повысить, но не понизить.

        Вставка идёт через `INSERT ... ON CONFLICT DO NOTHING`: два конкурентных
        accept одного и того же членства не должны ронять транзакцию в
        `IntegrityError` — гонка гасится в базе, а не проверкой перед вставкой.
        Без commit: принятие приглашения фиксирует всё одной транзакцией.
        """
        member = await self._workspaces.add_member_if_absent(
            workspace_id=workspace_id, user_id=user_id, role=role
        )
        if ROLE_RANK[role] > ROLE_RANK[WorkspaceRole(member.role)]:
            member.role = role
            await self._session.flush()

    async def get_member_role(self, workspace_id: UUID, user_id: UUID) -> WorkspaceRole | None:
        member = await self._workspaces.get_member(workspace_id, user_id)
        return WorkspaceRole(member.role) if member is not None else None

    async def memberships_of(self, user_id: UUID) -> Sequence[WorkspaceMember]:
        return await self._workspaces.memberships_of(user_id)

    async def _member(self, workspace_id: UUID, user_id: UUID) -> Member:
        found = await self._workspaces.get_member_with_user(workspace_id, user_id)
        if found is None:
            raise _member_not_found()
        return found

    @staticmethod
    def _guard_owner(ctx: AccessContext, *roles: WorkspaceRole) -> None:
        """Роль владельца назначает, снимает и исключает только владелец."""
        if WorkspaceRole.OWNER in roles and ctx.role < EffectiveRole.OWNER:
            raise ApiError(
                403,
                "insufficient_role",
                "Роль владельца меняет только владелец",
                {"required": "owner"},
            )

    async def _ensure_other_owner(self, workspace_id: UUID) -> None:
        if await self._workspaces.count_owners_locked(workspace_id) <= 1:
            raise ApiError(
                409, "last_owner", "У рабочего пространства должен остаться хотя бы один владелец"
            )

    # --- Для админ-панели: права проверяет вызывающий (`core/admin_access.py`) -------

    async def all(self) -> Sequence[Workspace]:
        return await self._workspaces.all()

    async def count(self) -> int:
        return await self._workspaces.count()

    async def member_counts(self, ids: Collection[UUID]) -> dict[UUID, int]:
        return await self._workspaces.member_counts(ids)

    async def owners_of(self, ids: Collection[UUID]) -> dict[UUID, list[User]]:
        return await self._workspaces.owners_of(ids)

    async def members_of(self, workspace_id: UUID) -> list[Member]:
        return await self._workspaces.list_members(workspace_id)

    async def sole_owned_by(self, user_id: UUID) -> Sequence[Workspace]:
        return await self._workspaces.sole_owned_by(user_id)

    async def drop_user(self, user_id: UUID) -> None:
        """Человек уходит из всех пространств — при удалении учётной записи. Без commit."""
        await self._workspaces.delete_memberships_of(user_id)

    async def delete_by_admin(self, workspace_id: UUID) -> None:
        """Удаление со всем содержимым по решению администратора инстанса. Без commit."""
        await self._workspaces.delete(workspace_id)

    async def make_owner(self, workspace_id: UUID, user_id: UUID) -> list[UUID]:
        """Аварийная передача владения: `user_id` становится владельцем (прежние
        остаются). Возвращает прежних владельцев — их надо уведомить. Без commit."""
        previous = [
            user.id
            for user in (await self._workspaces.owners_of([workspace_id])).get(workspace_id, [])
        ]
        member = await self._workspaces.add_member_if_absent(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.OWNER
        )
        member.role = WorkspaceRole.OWNER
        await self._session.flush()
        return [owner for owner in previous if owner != user_id]

    async def get_many(self, ids: Collection[UUID]) -> Sequence[Workspace]:
        return await self._workspaces.get_many(ids)
