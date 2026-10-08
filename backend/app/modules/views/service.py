"""Бизнес-правила views: права трёх scope и выполнение.

Права view не укладываются в «минимальную роль на объекте»: личный view виден только
владельцу, командный правит автор или лид, общий — автор или admin. Поэтому проверка
здесь, явно, поверх `resolve_access` к workspace и команде. Невидимый view — 404,
видимый без права изменения — 403.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ViewScope, WorkspaceRole
from app.core.errors import ApiError
from app.core.permissions import (
    AccessContext,
    EffectiveRole,
    Permission,
    compute_effective_role,
    load_access,
    resolve_access,
)
from app.core.principal import WRITE, Principal
from app.modules.tasks.models import Task
from app.modules.tasks.ordering import SortSpec
from app.modules.tasks.schemas import TaskGroup
from app.modules.tasks.service import TaskService
from app.modules.teams.service import TeamService
from app.modules.views.filters import FilterContext, FilterError, parse_filters, translate
from app.modules.views.models import View
from app.modules.views.repository import ViewRepository
from app.modules.views.schemas import ViewCreate, ViewUpdate, filters_json


def _not_found() -> ApiError:
    return ApiError(404, "view_not_found", "View не найден")


def _require_write(principal: Principal) -> None:
    if WRITE not in principal.scopes:
        raise ApiError(403, "insufficient_scope", "Токен выдан только на чтение")


class ViewService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._views = ViewRepository(session)

    async def list_visible(
        self, principal: Principal, workspace_id: UUID
    ) -> list[tuple[View, bool]]:
        ctx = await resolve_access(
            self._session,
            principal,
            on="workspace",
            object_id=workspace_id,
            permission=Permission.WORKSPACE_READ,
        )
        teams = await TeamService(self._session).list_visible(ctx)
        views = await self._views.list_visible(
            workspace_id,
            principal.user_id,
            team_ids=[team.id for team in teams],
            include_workspace=ctx.workspace_role != WorkspaceRole.GUEST,
        )
        return [(view, await self._can_edit(ctx, view)) for view in views]

    async def create(self, principal: Principal, data: ViewCreate) -> tuple[View, bool]:
        _require_write(principal)
        if data.scope == ViewScope.TEAM:
            ctx = await resolve_access(
                self._session,
                principal,
                on="team",
                object_id=data.team_id,
                permission=Permission.VIEW_CREATE_TEAM,
            )
            if ctx.workspace_id != data.workspace_id:
                raise ApiError(404, "team_not_found", "Команда не найдена")
        else:
            permission = (
                Permission.VIEW_CREATE_WORKSPACE
                if data.scope == ViewScope.WORKSPACE
                else Permission.WORKSPACE_READ
            )
            ctx = await resolve_access(
                self._session,
                principal,
                on="workspace",
                object_id=data.workspace_id,
                permission=permission,
            )

        owner_id = principal.user_id if data.scope == ViewScope.USER else None
        position = data.position
        if position is None:
            position = await self._views.next_position(
                ctx.workspace_id, data.scope, owner_id, data.team_id
            )
        now = datetime.now(UTC)
        view = await self._views.add(
            View(
                workspace_id=ctx.workspace_id,
                scope=data.scope,
                owner_id=owner_id,
                team_id=data.team_id,
                name=data.name,
                description=data.description,
                icon=data.icon,
                color=data.color,
                filters=filters_json(data.filters),
                group_by=data.group_by,
                sort_by=data.sort_by,
                sort_direction=data.sort_direction,
                layout=data.layout,
                position=position,
                created_by=principal.user_id,
                created_at=now,
                updated_at=now,
            )
        )
        await self._session.commit()
        return view, True

    async def get(self, principal: Principal, view_id: UUID | None) -> tuple[View, bool]:
        view, ctx = await self._visible(principal, view_id)
        return view, await self._can_edit(ctx, view)

    async def update(
        self, principal: Principal, view_id: UUID | None, data: ViewUpdate
    ) -> tuple[View, bool]:
        _require_write(principal)
        view = await self._editable(principal, view_id)
        changes = data.model_dump(exclude_unset=True)
        if data.filters is not None:
            changes["filters"] = filters_json(data.filters)
        for field, value in changes.items():
            setattr(view, field, value)
        if changes:
            view.updated_at = datetime.now(UTC)
            await self._session.commit()
        return view, True

    async def delete(self, principal: Principal, view_id: UUID | None) -> None:
        _require_write(principal)
        view = await self._editable(principal, view_id)
        await self._views.delete(view)
        await self._session.commit()

    async def run(
        self,
        principal: Principal,
        view_id: UUID | None,
        *,
        group: str | None,
        cursor: str | None,
        limit: int,
        expand: frozenset[str],
    ) -> tuple[View, list[TaskGroup]]:
        view, ctx = await self._visible(principal, view_id)
        # Повторная проверка грамматики: сохранённый view мог устареть вместе с ней.
        try:
            conditions = parse_filters(view.filters)
        except FilterError as error:
            raise ApiError(
                400,
                "invalid_filter",
                f"Фильтр view больше не по грамматике: {error.message}",
                {"field": error.field},
            ) from error
        today = datetime.now(UTC).date()
        sql = translate(conditions, FilterContext(user_id=principal.user_id, today=today))
        if view.scope == ViewScope.TEAM:
            sql.append(Task.team_id == view.team_id)
        groups = await TaskService(self._session).run_query(
            ctx,
            sql,
            SortSpec(view.sort_by, view.sort_direction),
            group_by=view.group_by,
            group=group,
            cursor=cursor,
            limit=limit,
            expand=expand,
        )
        return view, groups

    # --- Права -----------------------------------------------------------------

    async def _visible(
        self, principal: Principal, view_id: UUID | None
    ) -> tuple[View, AccessContext]:
        """View и контекст его workspace — если view виден; иначе 404."""
        view = await self._views.get(view_id) if view_id else None
        if view is None:
            raise _not_found()
        try:
            ctx = await resolve_access(
                self._session,
                principal,
                on="workspace",
                object_id=view.workspace_id,
                permission=Permission.WORKSPACE_READ,
            )
        except ApiError as error:
            raise _not_found() from error

        match view.scope:
            case ViewScope.USER:
                visible = view.owner_id == principal.user_id
            case ViewScope.TEAM:
                visible = (await self._team_role(principal, view)) is not None
            case _:
                visible = ctx.workspace_role != WorkspaceRole.GUEST
        if not visible:
            raise _not_found()
        return view, ctx

    async def _editable(self, principal: Principal, view_id: UUID | None) -> View:
        view, ctx = await self._visible(principal, view_id)
        if not await self._can_edit(ctx, view):
            raise ApiError(
                403,
                "insufficient_role",
                "Менять этот view может его автор или администратор",
                {"required": "admin"},
            )
        return view

    async def _can_edit(self, ctx: AccessContext, view: View) -> bool:
        if view.scope == ViewScope.USER:
            return view.owner_id == ctx.principal.user_id
        if view.created_by == ctx.principal.user_id:
            return True
        if view.scope == ViewScope.TEAM:
            role = await self._team_role(ctx.principal, view)
            return role is not None and role >= EffectiveRole.ADMIN
        return ctx.role >= EffectiveRole.ADMIN

    async def _team_role(self, principal: Principal, view: View) -> EffectiveRole | None:
        """Эффективная роль в команде view; ниже участника — view не виден."""
        assert view.team_id is not None
        row = await load_access(self._session, principal.user_id, "team", view.team_id)
        role = compute_effective_role(row) if row is not None else None
        return role if role is not None and role >= EffectiveRole.MEMBER else None
