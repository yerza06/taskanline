"""Авторизация внутри рабочего пространства.

Роль считается одним запросом с тремя LEFT JOIN (`load_access`) и чистой функцией
от его результата (`compute_effective_role`). Кэша нет: он придёт с Redis на
этапе 9 и навесится снаружи одной правкой, а до тех пор смена роли действует
немедленно.

Два правила ответа. Нет доступа — 404: существование чужого объекта не
подтверждается. 403 — только когда объект виден, а роли на действие не хватает.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.enums import ProjectRole, TeamRole, WorkspaceRole
from app.core.errors import ApiError
from app.core.principal import WRITE, CurrentPrincipal, Principal


class EffectiveRole(IntEnum):
    """Единая шкала возможностей трёх уровней (§6.2).

    `GUEST` — ступень ниже шкалы спеки: гость видит само рабочее пространство
    и больше ничего. На уровнях команды и проекта её не бывает.
    """

    GUEST = 0
    VIEWER = 1
    MEMBER = 2
    ADMIN = 3
    OWNER = 4


AccessTarget = Literal["workspace", "team", "project"]


@dataclass(frozen=True)
class AccessRow:
    """Результат `load_access`: где объект и кем в нём числится пользователь."""

    level: AccessTarget
    workspace_id: UUID
    team_id: UUID | None
    project_id: UUID | None
    workspace_role: WorkspaceRole | None
    # None — у объекта нет команды (сам workspace).
    team_is_private: bool | None
    team_role: TeamRole | None
    project_role: ProjectRole | None


_TEAM_ROLES = {TeamRole.LEAD: EffectiveRole.ADMIN, TeamRole.MEMBER: EffectiveRole.MEMBER}
_PROJECT_ROLES = {
    ProjectRole.ADMIN: EffectiveRole.ADMIN,
    ProjectRole.MEMBER: EffectiveRole.MEMBER,
    ProjectRole.VIEWER: EffectiveRole.VIEWER,
}


def compute_effective_role(row: AccessRow) -> EffectiveRole | None:
    """Максимум из ролей трёх уровней; `None` — доступа нет."""
    if row.workspace_role is None:
        return None

    candidates: list[EffectiveRole] = []
    match row.workspace_role:
        case WorkspaceRole.OWNER:
            candidates.append(EffectiveRole.OWNER)
        case WorkspaceRole.ADMIN:
            candidates.append(EffectiveRole.ADMIN)
        case WorkspaceRole.MEMBER:
            # Приватная команда невидима рядовому участнику: только явное членство.
            if not row.team_is_private:
                candidates.append(EffectiveRole.MEMBER)
        case WorkspaceRole.GUEST:
            # Гость не получает ничего по умолчанию — это и делает возможным
            # сценарий подрядчика. Видно ему только само пространство.
            if row.level == "workspace":
                candidates.append(EffectiveRole.GUEST)

    if row.team_role is not None:
        candidates.append(_TEAM_ROLES[row.team_role])
    if row.project_role is not None:
        candidates.append(_PROJECT_ROLES[row.project_role])

    return max(candidates, default=None)


class Permission(StrEnum):
    """Действия из матрицы §6.3. Минимальная роль каждого — в `MIN_ROLE`."""

    WORKSPACE_READ = "workspace.read"
    WORKSPACE_UPDATE = "workspace.update"
    WORKSPACE_DELETE = "workspace.delete"
    WORKSPACE_TRANSFER = "workspace.transfer"
    WORKSPACE_MEMBERS_READ = "workspace.members.read"
    WORKSPACE_MEMBERS_MANAGE = "workspace.members.manage"
    WORKSPACE_INVITE = "workspace.invite"
    WORKSPACE_INVITATIONS_READ = "workspace.invitations.read"
    TEAM_CREATE = "team.create"
    TEAM_READ = "team.read"
    TEAM_UPDATE = "team.update"
    TEAM_DELETE = "team.delete"
    TEAM_MEMBERS_MANAGE = "team.members.manage"
    TEAM_INVITE = "team.invite"
    PROJECT_CREATE = "project.create"
    PROJECT_READ = "project.read"
    PROJECT_UPDATE = "project.update"
    PROJECT_ARCHIVE = "project.archive"
    PROJECT_DELETE = "project.delete"
    PROJECT_MEMBERS_MANAGE = "project.members.manage"
    PROJECT_INVITE = "project.invite"


MIN_ROLE: dict[Permission, EffectiveRole] = {
    Permission.WORKSPACE_READ: EffectiveRole.GUEST,
    Permission.WORKSPACE_UPDATE: EffectiveRole.ADMIN,
    Permission.WORKSPACE_DELETE: EffectiveRole.OWNER,
    Permission.WORKSPACE_TRANSFER: EffectiveRole.OWNER,
    Permission.WORKSPACE_MEMBERS_READ: EffectiveRole.MEMBER,
    Permission.WORKSPACE_MEMBERS_MANAGE: EffectiveRole.ADMIN,
    Permission.WORKSPACE_INVITE: EffectiveRole.ADMIN,
    Permission.WORKSPACE_INVITATIONS_READ: EffectiveRole.ADMIN,
    Permission.TEAM_CREATE: EffectiveRole.ADMIN,
    Permission.TEAM_READ: EffectiveRole.MEMBER,
    Permission.TEAM_UPDATE: EffectiveRole.ADMIN,
    Permission.TEAM_DELETE: EffectiveRole.OWNER,
    Permission.TEAM_MEMBERS_MANAGE: EffectiveRole.ADMIN,
    Permission.TEAM_INVITE: EffectiveRole.ADMIN,
    Permission.PROJECT_CREATE: EffectiveRole.MEMBER,
    Permission.PROJECT_READ: EffectiveRole.VIEWER,
    Permission.PROJECT_UPDATE: EffectiveRole.MEMBER,
    Permission.PROJECT_ARCHIVE: EffectiveRole.ADMIN,
    Permission.PROJECT_DELETE: EffectiveRole.ADMIN,
    Permission.PROJECT_MEMBERS_MANAGE: EffectiveRole.ADMIN,
    Permission.PROJECT_INVITE: EffectiveRole.ADMIN,
}

# Всё остальное меняет данные и требует scope `write`.
READ_PERMISSIONS = frozenset(
    {
        Permission.WORKSPACE_READ,
        Permission.WORKSPACE_MEMBERS_READ,
        Permission.WORKSPACE_INVITATIONS_READ,
        Permission.TEAM_READ,
        Permission.PROJECT_READ,
    }
)

_NOT_FOUND: dict[AccessTarget, str] = {
    "workspace": "Рабочее пространство не найдено",
    "team": "Команда не найдена",
    "project": "Проект не найден",
}


@dataclass(frozen=True)
class AccessContext:
    """Что получает эндпоинт после проверки прав: где объект и какая роль."""

    principal: Principal
    workspace_id: UUID
    team_id: UUID | None
    project_id: UUID | None
    role: EffectiveRole

    @property
    def team(self) -> UUID:
        assert self.team_id is not None, "контекст не уровня команды"
        return self.team_id

    @property
    def project(self) -> UUID:
        assert self.project_id is not None, "контекст не уровня проекта"
        return self.project_id


async def load_access(
    session: AsyncSession, user_id: UUID, on: AccessTarget, object_id: UUID
) -> AccessRow | None:
    """Один запрос: объект и три членства пользователя. `None` — объекта нет.

    Модели импортируются внутри: модули зависят от core, и обратная связь на
    уровне модуля замкнула бы импорт в кольцо.
    """
    from app.modules.projects.models import Project, ProjectMember
    from app.modules.teams.models import Team, TeamMember
    from app.modules.workspaces.models import Workspace, WorkspaceMember

    if on == "workspace":
        ws_stmt = (
            select(Workspace.id, WorkspaceMember.role)
            .select_from(Workspace)
            .outerjoin(
                WorkspaceMember,
                and_(
                    WorkspaceMember.workspace_id == Workspace.id,
                    WorkspaceMember.user_id == user_id,
                ),
            )
            .where(Workspace.id == object_id)
        )
        ws_row = (await session.execute(ws_stmt)).one_or_none()
        if ws_row is None:
            return None
        return AccessRow(
            level="workspace",
            workspace_id=ws_row[0],
            team_id=None,
            project_id=None,
            workspace_role=_enum(WorkspaceRole, ws_row[1]),
            team_is_private=None,
            team_role=None,
            project_role=None,
        )

    in_workspace = and_(
        WorkspaceMember.workspace_id == Team.workspace_id, WorkspaceMember.user_id == user_id
    )
    in_team = and_(TeamMember.team_id == Team.id, TeamMember.user_id == user_id)

    if on == "team":
        team_stmt = (
            select(
                Team.workspace_id, Team.id, Team.is_private, WorkspaceMember.role, TeamMember.role
            )
            .select_from(Team)
            .outerjoin(WorkspaceMember, in_workspace)
            .outerjoin(TeamMember, in_team)
            .where(Team.id == object_id)
        )
        team_row = (await session.execute(team_stmt)).one_or_none()
        if team_row is None:
            return None
        return AccessRow(
            level="team",
            workspace_id=team_row[0],
            team_id=team_row[1],
            project_id=None,
            workspace_role=_enum(WorkspaceRole, team_row[3]),
            team_is_private=team_row[2],
            team_role=_enum(TeamRole, team_row[4]),
            project_role=None,
        )

    project_stmt = (
        select(
            Project.workspace_id,
            Project.team_id,
            Project.id,
            Team.is_private,
            WorkspaceMember.role,
            TeamMember.role,
            ProjectMember.role,
        )
        .select_from(Project)
        .join(Team, Team.id == Project.team_id)
        .outerjoin(WorkspaceMember, in_workspace)
        .outerjoin(TeamMember, in_team)
        .outerjoin(
            ProjectMember,
            and_(ProjectMember.project_id == Project.id, ProjectMember.user_id == user_id),
        )
        .where(Project.id == object_id)
    )
    project_row = (await session.execute(project_stmt)).one_or_none()
    if project_row is None:
        return None
    return AccessRow(
        level="project",
        workspace_id=project_row[0],
        team_id=project_row[1],
        project_id=project_row[2],
        workspace_role=_enum(WorkspaceRole, project_row[4]),
        team_is_private=project_row[3],
        team_role=_enum(TeamRole, project_row[5]),
        project_role=_enum(ProjectRole, project_row[6]),
    )


def _enum[E: StrEnum](kind: type[E], value: str | None) -> E | None:
    return kind(value) if value is not None else None


async def resolve_access(
    session: AsyncSession,
    principal: Principal,
    *,
    on: AccessTarget,
    object_id: UUID | None,
    permission: Permission,
) -> AccessContext:
    """Проверка права на объект. Порядок отказов: scope → существование → роль."""
    if permission not in READ_PERMISSIONS and WRITE not in principal.scopes:
        raise ApiError(403, "insufficient_scope", "Токен выдан только на чтение")

    row = await load_access(session, principal.user_id, on, object_id) if object_id else None
    role = compute_effective_role(row) if row is not None else None
    if row is None or role is None:
        raise ApiError(404, f"{on}_not_found", _NOT_FOUND[on])

    minimum = MIN_ROLE[permission]
    if role < minimum:
        raise ApiError(
            403,
            "insufficient_role",
            "Недостаточно прав для этого действия",
            {"required": minimum.name.lower()},
        )

    return AccessContext(
        principal=principal,
        workspace_id=row.workspace_id,
        team_id=row.team_id,
        project_id=row.project_id,
        role=role,
    )


def _path_uuid(request: Request, name: str) -> UUID | None:
    """Не-UUID в пути — такого объекта нет (404), а не ошибка формата (422)."""
    try:
        return UUID(request.path_params[name])
    except ValueError:
        return None


def require_permission(
    permission: Permission, *, on: AccessTarget
) -> Callable[..., Awaitable[AccessContext]]:
    """Зависимость FastAPI: `Depends(require_permission(Permission.X, on="team"))`.

    Id объекта берётся из параметра пути `{on}_id` — у всех маршрутов этапа он
    называется именно так.
    """

    async def dependency(
        request: Request,
        principal: CurrentPrincipal,
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> AccessContext:
        return await resolve_access(
            session,
            principal,
            on=on,
            object_id=_path_uuid(request, f"{on}_id"),
            permission=permission,
        )

    return dependency
