"""Авторизация внутри рабочего пространства.

Роль считается одним запросом с тремя LEFT JOIN (`load_access`) и чистой функцией
от его результата (`compute_effective_role`). Кэша нет: он придёт с Redis на
этапе 9 и навесится снаружи одной правкой, а до тех пор смена роли действует
немедленно.

Два правила ответа. Нет доступа — 404: существование чужого объекта не
подтверждается. 403 — только когда объект виден, а роли на действие не хватает.
"""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import ColumnElement, Uuid, and_, cast, exists, false, func, null, or_, select, true
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


AccessTarget = Literal["workspace", "team", "project", "task", "state", "label", "comment"]
# Уровень, на котором считается роль: задача — уровень своего проекта или команды,
# статус — команды, метка — команды или всего workspace.
AccessLevel = Literal["workspace", "team", "project"]


@dataclass(frozen=True)
class AccessRow:
    """Результат `load_access`: где объект и кем в нём числится пользователь."""

    level: AccessLevel
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
    STATE_MANAGE = "state.manage"
    LABEL_MANAGE = "label.manage"
    TASK_READ = "task.read"
    TASK_CREATE = "task.create"
    TASK_UPDATE = "task.update"
    TASK_DELETE = "task.delete"
    TASK_RESTORE = "task.restore"
    COMMENT_CREATE = "comment.create"
    # Изменить и удалить комментарий: видимость задачи и scope `write` здесь, а
    # «автор или admin» — в сервисе, роль одна на это правило не выражается.
    COMMENT_EDIT = "comment.edit"


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
    Permission.STATE_MANAGE: EffectiveRole.ADMIN,
    Permission.LABEL_MANAGE: EffectiveRole.MEMBER,
    Permission.TASK_READ: EffectiveRole.VIEWER,
    Permission.TASK_CREATE: EffectiveRole.MEMBER,
    Permission.TASK_UPDATE: EffectiveRole.MEMBER,
    Permission.TASK_DELETE: EffectiveRole.MEMBER,
    Permission.TASK_RESTORE: EffectiveRole.ADMIN,
    Permission.COMMENT_CREATE: EffectiveRole.MEMBER,
    Permission.COMMENT_EDIT: EffectiveRole.VIEWER,
}

# Всё остальное меняет данные и требует scope `write`.
READ_PERMISSIONS = frozenset(
    {
        Permission.WORKSPACE_READ,
        Permission.WORKSPACE_MEMBERS_READ,
        Permission.WORKSPACE_INVITATIONS_READ,
        Permission.TEAM_READ,
        Permission.PROJECT_READ,
        Permission.TASK_READ,
    }
)

_NOT_FOUND: dict[AccessTarget, str] = {
    "workspace": "Рабочее пространство не найдено",
    "team": "Команда не найдена",
    "project": "Проект не найден",
    "task": "Задача не найдена",
    "state": "Статус не найден",
    "label": "Метка не найдена",
    "comment": "Комментарий не найден",
}


@dataclass(frozen=True)
class AccessContext:
    """Что получает эндпоинт после проверки прав: где объект и какая роль."""

    principal: Principal
    workspace_id: UUID
    team_id: UUID | None
    project_id: UUID | None
    role: EffectiveRole
    # Роль в самом workspace: по ней строится видимость соседних объектов —
    # задач в списке, связей, подзадач.
    workspace_role: WorkspaceRole
    # Id объекта проверки: у задачи — уже разрешённый из ключа `ENG-142` UUID.
    object_id: UUID

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

    anchor = _anchor(on, object_id).subquery()
    stmt = (
        select(
            anchor.c.workspace_id,
            anchor.c.team_id,
            Team.id,
            Project.id,
            Team.is_private,
            WorkspaceMember.role,
            TeamMember.role,
            ProjectMember.role,
        )
        .select_from(anchor)
        # Защита в глубину: команда и проект обязаны лежать в том же пространстве,
        # а проект — в той же команде. Это гарантируют сервисы, но JOIN не должен
        # полагаться только на приложение — рассинхронизированные данные не должны
        # стать видны никому.
        .outerjoin(
            Team, and_(Team.id == anchor.c.team_id, Team.workspace_id == anchor.c.workspace_id)
        )
        .outerjoin(
            Project,
            and_(
                Project.id == anchor.c.project_id,
                Project.team_id == anchor.c.team_id,
                Project.workspace_id == anchor.c.workspace_id,
            ),
        )
        .outerjoin(
            WorkspaceMember,
            and_(
                WorkspaceMember.workspace_id == anchor.c.workspace_id,
                WorkspaceMember.user_id == user_id,
            ),
        )
        .outerjoin(TeamMember, and_(TeamMember.team_id == Team.id, TeamMember.user_id == user_id))
        .outerjoin(
            ProjectMember,
            and_(ProjectMember.project_id == Project.id, ProjectMember.user_id == user_id),
        )
    )
    found = (await session.execute(stmt)).one_or_none()
    if found is None:
        return None
    (workspace_id, anchor_team, team_id, project_id, is_private) = found[:5]
    ws_role, team_role, project_role = found[5:]
    if anchor_team is not None and team_id is None:
        # Команда объекта лежит в другом пространстве — объекта нет ни для кого.
        return None
    if on == "project" and project_id is None:
        return None

    # Проект чужой команды у задачи отбрасывается JOIN-ом: роль считается по команде.
    level: AccessLevel = "workspace" if team_id is None else "project" if project_id else "team"
    return AccessRow(
        level=level,
        workspace_id=workspace_id,
        team_id=team_id,
        project_id=project_id,
        workspace_role=_enum(WorkspaceRole, ws_role),
        team_is_private=is_private,
        team_role=_enum(TeamRole, team_role),
        project_role=_enum(ProjectRole, project_role),
    )


def _anchor(on: AccessTarget, object_id: UUID) -> Any:
    """Где лежит объект: `(workspace_id, team_id, project_id)` одной строкой.

    Модели импортируются внутри по той же причине, что и в `load_access`.
    """
    from app.modules.comments.models import Comment
    from app.modules.labels.models import Label
    from app.modules.projects.models import Project
    from app.modules.states.models import WorkflowState
    from app.modules.tasks.models import Task
    from app.modules.teams.models import Team

    # Типизированный NULL: без приведения PostgreSQL считает его text и не сравнит с uuid.
    no_project = cast(null(), Uuid).label("project_id")
    match on:
        case "team":
            return select(Team.workspace_id, Team.id.label("team_id"), no_project).where(
                Team.id == object_id
            )
        case "project":
            return select(
                Project.workspace_id, Project.team_id, Project.id.label("project_id")
            ).where(Project.id == object_id)
        case "task":
            return select(Task.workspace_id, Task.team_id, Task.project_id).where(
                Task.id == object_id
            )
        case "state":
            return select(WorkflowState.workspace_id, WorkflowState.team_id, no_project).where(
                WorkflowState.id == object_id
            )
        case "label":
            return select(Label.workspace_id, Label.team_id, no_project).where(
                Label.id == object_id
            )
        case "comment":
            return (
                select(Comment.workspace_id, Task.team_id, Task.project_id)
                .join(
                    Task,
                    and_(Task.id == Comment.task_id, Task.workspace_id == Comment.workspace_id),
                )
                .where(Comment.id == object_id)
            )
    raise AssertionError(on)


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
    if row is None or role is None or row.workspace_role is None or object_id is None:
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
        workspace_role=row.workspace_role,
        object_id=object_id,
    )


TASK_KEY = re.compile(r"^([A-Za-z]{2,5})-([1-9][0-9]{0,8})$")


async def find_task_by_key(
    session: AsyncSession, user_id: UUID, key: str, *, workspace_id: UUID | None = None
) -> UUID | None:
    """`ENG-142` → id задачи среди видимых пользователю.

    Ключ уникален внутри workspace, а не глобально. Найдено в нескольких видимых
    пространствах — `409 task_key_ambiguous` со списком пространств; уточняет
    `workspace_id`. Невидимые кандидаты не считаются и в список не попадают: иначе
    ключ подтверждал бы существование задачи в приватной команде.

    Удалённые задачи находятся тоже: восстанавливать их тоже нужно по ключу.
    """
    from app.modules.tasks.models import Task
    from app.modules.teams.models import Team
    from app.modules.workspaces.models import WorkspaceMember

    match = TASK_KEY.match(key)
    if match is None:
        return None
    stmt = (
        select(Task.id, Task.workspace_id)
        .join(Team, and_(Team.id == Task.team_id, Team.workspace_id == Task.workspace_id))
        .join(
            WorkspaceMember,
            and_(
                WorkspaceMember.workspace_id == Task.workspace_id,
                WorkspaceMember.user_id == user_id,
            ),
        )
        .where(func.upper(Team.key) == match.group(1).upper(), Task.number == int(match.group(2)))
    )
    if workspace_id is not None:
        stmt = stmt.where(Task.workspace_id == workspace_id)

    visible: list[tuple[UUID, UUID]] = []
    for task_id, task_workspace in (await session.execute(stmt)).tuples():
        row = await load_access(session, user_id, "task", task_id)
        if row is not None and compute_effective_role(row) is not None:
            visible.append((task_id, task_workspace))

    if len(visible) > 1:
        raise ApiError(
            409,
            "task_key_ambiguous",
            f"Ключ {key.upper()} есть в нескольких рабочих пространствах — укажите workspace_id",
            {"workspace_ids": sorted(str(space) for _, space in visible)},
        )
    return visible[0][0] if visible else None


def task_visibility(workspace_role: WorkspaceRole, user_id: UUID) -> ColumnElement[bool]:
    """Условие «задача видна» для списков — та же логика, что `compute_effective_role`.

    Роль в workspace известна заранее (список требует доступа к пространству),
    поэтому ветвление по ней — в Python, а в SQL остаются только членства.
    Тест `test_permissions_tasks` сверяет обе реализации на всех формах членства.
    """
    from app.modules.projects.models import ProjectMember
    from app.modules.tasks.models import Task
    from app.modules.teams.models import Team, TeamMember

    if workspace_role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
        return true()

    in_team = exists().where(TeamMember.team_id == Task.team_id, TeamMember.user_id == user_id)
    in_project = exists().where(
        ProjectMember.project_id == Task.project_id, ProjectMember.user_id == user_id
    )
    explicit = or_(in_team, in_project)
    if workspace_role == WorkspaceRole.MEMBER:
        public_team = exists().where(Team.id == Task.team_id, Team.is_private.is_(False))
        return or_(public_team, explicit)
    if workspace_role == WorkspaceRole.GUEST:
        return explicit
    return false()


def _path_uuid(request: Request, name: str) -> UUID | None:
    """Не-UUID в пути — такого объекта нет (404), а не ошибка формата (422)."""
    try:
        return UUID(request.path_params[name])
    except ValueError:
        return None


async def task_ref_to_id(
    session: AsyncSession, user_id: UUID, ref: str, *, workspace_id: UUID | None = None
) -> UUID | None:
    """Ссылка на задачу — UUID или ключ `ENG-142`. `None` — такой задачи не видно."""
    try:
        return UUID(ref)
    except ValueError:
        return await find_task_by_key(session, user_id, ref, workspace_id=workspace_id)


def require_permission(
    permission: Permission, *, on: AccessTarget
) -> Callable[..., Awaitable[AccessContext]]:
    """Зависимость FastAPI: `Depends(require_permission(Permission.X, on="team"))`.

    Id объекта берётся из параметра пути `{on}_id` — у всех маршрутов он называется
    именно так. У задачи там же может стоять ключ `ENG-142`; неоднозначный ключ
    уточняется query-параметром `workspace_id`.
    """

    async def dependency(
        request: Request,
        principal: CurrentPrincipal,
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> AccessContext:
        if on == "task":
            # Scope — раньше поиска по ключу: порядок отказов не зависит от формы ссылки.
            if permission not in READ_PERMISSIONS and WRITE not in principal.scopes:
                raise ApiError(403, "insufficient_scope", "Токен выдан только на чтение")
            hint = _query_uuid(request, "workspace_id")
            object_id = await task_ref_to_id(
                session, principal.user_id, request.path_params["task_id"], workspace_id=hint
            )
        else:
            object_id = _path_uuid(request, f"{on}_id")
        return await resolve_access(
            session, principal, on=on, object_id=object_id, permission=permission
        )

    return dependency


def _query_uuid(request: Request, name: str) -> UUID | None:
    value = request.query_params.get(name)
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        raise ApiError(400, "invalid_workspace_id", "workspace_id должен быть UUID") from None


async def resolve_team_read(
    session: AsyncSession, principal: Principal, team_id: UUID | None
) -> AccessContext:
    """Чтение того, что команда делит со своими проектами: статусы и метки.

    Подрядчик — участник проекта без членства в команде — команду не видит, но без
    её статусов и меток он не может работать со своими задачами. Поэтому сюда
    пускает и `TEAM_READ`, и членство в любом проекте этой команды.
    """
    from app.modules.projects.models import Project, ProjectMember

    try:
        return await resolve_access(
            session, principal, on="team", object_id=team_id, permission=Permission.TEAM_READ
        )
    except ApiError as error:
        if error.status_code != 404 or team_id is None:
            raise
        project_id = await session.scalar(
            select(ProjectMember.project_id)
            .join(Project, Project.id == ProjectMember.project_id)
            .where(Project.team_id == team_id, ProjectMember.user_id == principal.user_id)
            .limit(1)
        )
        if project_id is None:
            raise
        return await resolve_access(
            session,
            principal,
            on="project",
            object_id=project_id,
            permission=Permission.PROJECT_READ,
        )


async def require_team_read(
    request: Request,
    principal: CurrentPrincipal,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccessContext:
    """Зависимость для `resolve_team_read`: id команды — из параметра пути `team_id`."""
    return await resolve_team_read(session, principal, _path_uuid(request, "team_id"))
