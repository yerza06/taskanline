"""Бизнес-правила админ-панели: люди, пространства, настройки, журнал.

Права проверены до сервиса — зависимостью `require_instance_role` (`core/admin_access.py`).
Здесь — инварианты, которые от роли не зависят:

- хотя бы один действующий `superadmin` есть всегда (`409 last_superadmin`);
- над тем, чья роль выше вашей, действовать нельзя: администратор не блокирует
  владельца инстанса;
- каждое изменение пишет запись в `admin_audit_log` в той же транзакции.

Данные других модулей — только через их сервисы, как и везде в проекте.
"""

import bisect
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.admin_access import RANK, AdminContext
from app.core.enums import (
    AuditAction,
    AuditTarget,
    InstanceRole,
    NotificationType,
    WorkspaceRole,
)
from app.core.errors import ApiError
from app.core.mail import MailMessage
from app.core.pagination import decode_cursor, encode_cursor, paginate
from app.core.security import issue_reauth_token, verify_password
from app.modules.activities.service import ActivityService
from app.modules.admin.models import AdminAuditLog
from app.modules.admin.repository import AuditRepository
from app.modules.admin.schemas import (
    AdminLogin,
    AdminMembership,
    AdminOwner,
    AdminSession,
    AdminToken,
    AdminUserDetail,
    AdminUserPage,
    AdminUserRow,
    AdminWorkspaceDetail,
    AdminWorkspaceMember,
    AdminWorkspacePage,
    AdminWorkspaceRow,
    AuditActor,
    AuditEntry,
    AuditFilters,
    AuditPage,
    SettingsRead,
    SettingsUpdate,
    Stats,
    UserCounts,
)
from app.modules.auth.service import AuthService
from app.modules.auth.token_service import ApiTokenService
from app.modules.instance.service import InstanceService
from app.modules.notifications.service import NotificationService
from app.modules.tasks.service import TaskService
from app.modules.teams.service import TeamService
from app.modules.users.models import User
from app.modules.users.service import UserService
from app.modules.workspaces.models import Workspace
from app.modules.workspaces.service import WorkspaceService

# Сколько неудачных подтверждений паролем подряд терпим, прежде чем закрыть сессию.
MAX_REAUTH_FAILURES = 3
WORKSPACE_SORTS = ("created", "name", "members", "tasks", "activity")


def _user_not_found() -> ApiError:
    return ApiError(404, "user_not_found", "Пользователь не найден")


def _workspace_not_found() -> ApiError:
    return ApiError(404, "workspace_not_found", "Рабочее пространство не найдено")


def _last_superadmin() -> ApiError:
    return ApiError(
        409,
        "last_superadmin",
        "Это последний действующий superadmin — сначала назначьте другого",
    )


def status_of(user: User) -> str:
    if user.deleted_at is not None:
        return "deleted"
    return "active" if user.is_active else "blocked"


def _row(user: User) -> AdminUserRow:
    return AdminUserRow(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        status=status_of(user),
        created_at=user.created_at,
        last_seen_at=user.last_seen_at,
    )


def _migration_head() -> str | None:
    """Последняя ревизия в коде — рядом с приложением лежат его миграции."""
    try:
        from alembic.script import ScriptDirectory

        migrations = Path(__file__).resolve().parents[3] / "migrations"
        return ScriptDirectory(str(migrations)).get_current_head()
    except Exception:
        return None


class AdminService:
    def __init__(self, session: AsyncSession, reauth_failures: dict[UUID, int]) -> None:
        self._session = session
        self._audit = AuditRepository(session)
        self._failures = reauth_failures
        self._users = UserService(session)
        self._auth = AuthService(session)
        self._tokens = ApiTokenService(session)
        self._workspaces = WorkspaceService(session)
        self._instance = InstanceService(session)

    # --- Журнал -------------------------------------------------------------------

    async def _record(
        self,
        ctx: AdminContext,
        action: AuditAction,
        *,
        target_type: AuditTarget | None = None,
        target_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Запись журнала — без commit, в транзакции самого действия."""
        await self._audit.add(
            AdminAuditLog(
                actor_id=ctx.user_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                payload=payload or {},
                ip=ctx.ip,
                user_agent=ctx.user_agent,
            )
        )

    async def audit_page(
        self, filters: AuditFilters, *, cursor: str | None, limit: int
    ) -> AuditPage:
        after = None
        if cursor is not None:
            created, entry_id = decode_cursor(cursor, 2)
            after = (datetime.fromisoformat(created), UUID(entry_id))
        rows = await self._audit.page(filters, after=after, limit=limit)
        items, next_cursor, has_more = paginate(rows, limit, lambda e: (e.created_at, e.id))
        actors = {u.id: u for u in await self._users.get_many({e.actor_id for e in items})}
        return AuditPage(
            items=[
                AuditEntry(
                    id=entry.id,
                    actor=AuditActor(
                        id=entry.actor_id,
                        email=actors[entry.actor_id].email,
                        full_name=actors[entry.actor_id].full_name,
                    ),
                    action=entry.action,
                    target_type=entry.target_type,
                    target_id=entry.target_id,
                    payload=entry.payload,
                    ip=str(entry.ip) if entry.ip is not None else None,
                    user_agent=entry.user_agent,
                    created_at=entry.created_at,
                )
                for entry in items
            ],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    # --- Сессия администратора ----------------------------------------------------

    async def session_info(
        self, ctx: AdminContext, *, reauth_until: datetime | None = None
    ) -> AdminSession:
        user = await self._users.get_active(ctx.user_id)
        return AdminSession(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            reauth_until=reauth_until or ctx.reauth_until,
        )

    async def open_session(self, ctx: AdminContext) -> AdminSession:
        """Вход в админку — запись `admin_login`."""
        await self._record(ctx, AuditAction.ADMIN_LOGIN)
        await self._session.commit()
        return await self.session_info(ctx)

    async def reauth(self, ctx: AdminContext, password: str) -> tuple[AdminSession, str]:
        """Подтверждение паролем на 15 минут. Третья неудача подряд закрывает все
        сессии администратора: открытый ноутбук не должен давать бесконечных попыток."""
        user = await self._users.get_active(ctx.user_id)
        if verify_password(user.password_hash, password):
            self._failures.pop(user.id, None)
            token, until = issue_reauth_token(user.id)
            return await self.session_info(ctx, reauth_until=until), token

        failures = self._failures.get(user.id, 0) + 1
        await self._record(
            ctx,
            AuditAction.REAUTH_FAILED,
            target_type=AuditTarget.USER,
            target_id=user.id,
            payload={"attempt": failures},
        )
        if failures >= MAX_REAUTH_FAILURES:
            self._failures.pop(user.id, None)
            await self._auth.revoke_sessions(user.id)
            await self._session.commit()
            raise ApiError(401, "session_terminated", "Три неверных пароля подряд — войдите заново")
        self._failures[user.id] = failures
        await self._session.commit()
        raise ApiError(
            403,
            "reauth_failed",
            "Неверный пароль",
            {"attempts_left": MAX_REAUTH_FAILURES - failures},
        )

    # --- Дашборд ------------------------------------------------------------------

    async def stats(self) -> Stats:
        counts = await self._users.status_counts()
        migration = await self._session.scalar(text("SELECT version_num FROM alembic_version"))
        return Stats(
            users=UserCounts(**counts),
            workspaces=await self._workspaces.count(),
            teams=await TeamService(self._session).count(),
            tasks=await TaskService(self._session).count(),
            version=__version__,
            migration=migration,
            migration_head=_migration_head(),
        )

    # --- Пользователи -------------------------------------------------------------

    async def users_page(
        self,
        *,
        query: str | None,
        role: InstanceRole | None,
        status: str | None,
        cursor: str | None,
        limit: int,
    ) -> AdminUserPage:
        after = None
        if cursor is not None:
            created, user_id = decode_cursor(cursor, 2)
            after = (datetime.fromisoformat(created), UUID(user_id))
        rows = await self._users.search(
            query=query, role=role, status=status, after=after, limit=limit
        )
        items, next_cursor, has_more = paginate(rows, limit, lambda u: (u.created_at, u.id))
        return AdminUserPage(
            items=[_row(user) for user in items], next_cursor=next_cursor, has_more=has_more
        )

    async def _user(self, user_id: UUID) -> User:
        user = await self._users.find(user_id)
        if user is None:
            raise _user_not_found()
        return user

    async def user_detail(self, user_id: UUID) -> AdminUserDetail:
        user = await self._user(user_id)
        memberships = await self._workspaces.memberships_of(user.id)
        spaces = {
            w.id: w for w in await self._workspaces.get_many([m.workspace_id for m in memberships])
        }
        return AdminUserDetail(
            **_row(user).model_dump(),
            memberships=[
                AdminMembership(
                    workspace_id=m.workspace_id,
                    workspace_name=spaces[m.workspace_id].name,
                    workspace_slug=spaces[m.workspace_id].slug,
                    role=WorkspaceRole(m.role),
                )
                for m in memberships
                if m.workspace_id in spaces
            ],
            tokens=[
                AdminToken.model_validate(token, from_attributes=True)
                for token in await self._tokens.list_all(user.id)
            ],
            logins=[
                AdminLogin.model_validate(event, from_attributes=True)
                for event in await self._auth.recent_logins(user.id)
            ],
        )

    async def _target(self, ctx: AdminContext, user_id: UUID) -> User:
        """Пользователь, над которым действует администратор: живой и не выше рангом."""
        user = await self._user(user_id)
        if user.deleted_at is not None:
            raise ApiError(409, "user_deleted", "Учётная запись уже удалена")
        if RANK[user.role] > RANK[ctx.role]:
            raise ApiError(
                403,
                "insufficient_role",
                "Нельзя действовать над тем, чья роль выше вашей",
                {"required": str(user.role)},
            )
        return user

    async def _guard_last_superadmin(self, user: User) -> None:
        """Нельзя убрать последнего действующего superadmin — ни блокировкой, ни сменой
        роли, ни удалением. Проверка под блокировкой строк против гонки двух админов."""
        if user.role != InstanceRole.SUPERADMIN or not user.is_active:
            return
        if await self._users.active_superadmins_locked() == [user.id]:
            raise _last_superadmin()

    async def block(self, ctx: AdminContext, user_id: UUID) -> AdminUserRow:
        """Блокировка гасит всё сразу: сессии и токены агентов. Заблокированный не
        доработает смену ни в открытой вкладке, ни руками своего агента."""
        user = await self._target(ctx, user_id)
        if user.is_active:
            await self._guard_last_superadmin(user)
            user.is_active = False
            user.updated_at = datetime.now(UTC)
            await self._auth.revoke_sessions(user.id)
            await self._tokens.revoke_all(user.id)
            await self._record(
                ctx, AuditAction.USER_BLOCKED, target_type=AuditTarget.USER, target_id=user.id,
                payload={"email": user.email},
            )  # fmt: skip
            await self._session.commit()
        return _row(user)

    async def unblock(self, ctx: AdminContext, user_id: UUID) -> AdminUserRow:
        """Токены, отозванные блокировкой, не возвращаются: человек выпустит новые."""
        user = await self._target(ctx, user_id)
        if not user.is_active:
            user.is_active = True
            user.updated_at = datetime.now(UTC)
            await self._record(
                ctx, AuditAction.USER_UNBLOCKED, target_type=AuditTarget.USER, target_id=user.id,
                payload={"email": user.email},
            )  # fmt: skip
            await self._session.commit()
        return _row(user)

    async def reset_password(self, ctx: AdminContext, user_id: UUID) -> MailMessage:
        user = await self._target(ctx, user_id)
        message = await self._auth.start_password_reset(user, requested_by=ctx.user_id)
        await self._record(
            ctx, AuditAction.PASSWORD_RESET_SENT, target_type=AuditTarget.USER, target_id=user.id,
            payload={"email": user.email},
        )  # fmt: skip
        await self._session.commit()
        return message

    async def revoke_token(self, ctx: AdminContext, user_id: UUID, token_id: UUID) -> None:
        user = await self._target(ctx, user_id)
        token = await self._tokens.revoke_for(token_id, user.id)
        await self._record(
            ctx, AuditAction.TOKEN_REVOKED, target_type=AuditTarget.USER, target_id=user.id,
            payload={"token_id": str(token.id), "name": token.name, "prefix": token.prefix},
        )  # fmt: skip
        await self._session.commit()

    async def change_role(
        self, ctx: AdminContext, user_id: UUID, role: InstanceRole
    ) -> AdminUserRow:
        user = await self._target(ctx, user_id)
        if user.role != role:
            if role != InstanceRole.SUPERADMIN:
                await self._guard_last_superadmin(user)
            previous = user.role
            user.role = role
            user.updated_at = datetime.now(UTC)
            await self._record(
                ctx, AuditAction.USER_ROLE_CHANGED, target_type=AuditTarget.USER,
                target_id=user.id, payload={"from": previous, "to": role, "email": user.email},
            )  # fmt: skip
            await self._session.commit()
        return _row(user)

    async def delete_user(self, ctx: AdminContext, user_id: UUID) -> None:
        """Удаление — анонимизация. Отказ, если человек — последний владелец живого
        пространства: сначала передать владение, иначе пространство осиротеет."""
        user = await self._target(ctx, user_id)
        orphans = await self._workspaces.sole_owned_by(user.id)
        if orphans:
            raise ApiError(
                409,
                "last_owner_of_workspace",
                "Пользователь — единственный владелец пространств; сначала передайте владение",
                {
                    "workspaces": [
                        {"id": str(w.id), "name": w.name, "slug": w.slug} for w in orphans
                    ]
                },
            )
        await self._guard_last_superadmin(user)
        email = user.email
        await self._auth.revoke_sessions(user.id)
        await self._tokens.revoke_all(user.id)
        await self._workspaces.drop_user(user.id)
        await self._users.anonymize(user)
        await self._record(
            ctx, AuditAction.USER_DELETED, target_type=AuditTarget.USER, target_id=user.id,
            payload={"email": email},
        )  # fmt: skip
        await self._session.commit()

    # --- Рабочие пространства -----------------------------------------------------

    async def _workspace_rows(self, spaces: Sequence[Workspace]) -> list[AdminWorkspaceRow]:
        ids = [w.id for w in spaces]
        members = await self._workspaces.member_counts(ids)
        owners = await self._workspaces.owners_of(ids)
        teams = await TeamService(self._session).counts_by_workspace(ids)
        tasks = await TaskService(self._session).counts_by_workspace(ids)
        activity = await ActivityService(self._session).last_at_by_workspace(ids)
        return [
            AdminWorkspaceRow(
                id=w.id,
                name=w.name,
                slug=w.slug,
                owners=[AdminOwner(user_id=u.id, email=u.email) for u in owners.get(w.id, [])],
                members=members.get(w.id, 0),
                teams=teams.get(w.id, 0),
                tasks=tasks.get(w.id, 0),
                created_at=w.created_at,
                last_activity_at=activity.get(w.id),
            )
            for w in spaces
        ]

    async def workspaces_page(
        self, *, query: str | None, sort: str, cursor: str | None, limit: int
    ) -> AdminWorkspacePage:
        """Сортировка по размеру и давности активности — так находятся брошенные.

        Счётчики живут в разных модулях, поэтому сортировка — в памяти, по всему
        списку. На self-hosted инстансе пространств сотни, не миллионы; когда это
        изменится, счётчики переедут в материализованное представление.
        """
        spaces = list(await self._workspaces.all())
        if query:
            needle = query.lower()
            spaces = [w for w in spaces if needle in w.name.lower() or needle in w.slug.lower()]
        rows = await self._workspace_rows(spaces)
        key = _workspace_key(sort)
        rows.sort(key=key)
        keys = [key(row) for row in rows]
        start = 0
        if cursor is not None:
            value, row_id = decode_cursor(cursor, 2)
            start = bisect.bisect_right(keys, _decode_key(sort, value, row_id))
        page = rows[start : start + limit]
        has_more = start + limit < len(rows)
        next_cursor = None
        if has_more and page:
            last = key(page[-1])
            next_cursor = encode_cursor(last[0], page[-1].id)
        return AdminWorkspacePage(items=page, next_cursor=next_cursor, has_more=has_more)

    async def _workspace(self, workspace_id: UUID) -> Workspace:
        found = await self._workspaces.find(workspace_id)
        if found is None:
            raise _workspace_not_found()
        return found

    async def workspace_detail(self, workspace_id: UUID) -> AdminWorkspaceDetail:
        """Участники и их роли — и ничего из содержимого: ни задач, ни проектов."""
        workspace = await self._workspace(workspace_id)
        (row,) = await self._workspace_rows([workspace])
        members = await self._workspaces.members_of(workspace.id)
        return AdminWorkspaceDetail(
            **row.model_dump(),
            member_list=[
                AdminWorkspaceMember(
                    user_id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    role=WorkspaceRole(member.role),
                )
                for member, user in members
            ],
        )

    async def delete_workspace(self, ctx: AdminContext, workspace_id: UUID) -> None:
        workspace = await self._workspace(workspace_id)
        payload = {"name": workspace.name, "slug": workspace.slug}
        await self._workspaces.delete_by_admin(workspace.id)
        await self._record(
            ctx, AuditAction.WORKSPACE_DELETED, target_type=AuditTarget.WORKSPACE,
            target_id=workspace_id, payload=payload,
        )  # fmt: skip
        await self._session.commit()

    async def grant_ownership(self, ctx: AdminContext, workspace_id: UUID) -> AdminWorkspaceDetail:
        """Аварийный вход внутрь чужого пространства — намеренно громкий: журнал плюс
        уведомление каждому прежнему владельцу. Тихий доступ был бы закладкой."""
        workspace = await self._workspace(workspace_id)
        previous = await self._workspaces.make_owner(workspace.id, ctx.user_id)
        notifications = NotificationService(self._session)
        for owner_id in previous:
            await notifications.notify(
                workspace_id=workspace.id,
                user_id=owner_id,
                kind=NotificationType.OWNERSHIP_GRANTED,
                actor_id=ctx.user_id,
            )
        await self._record(
            ctx, AuditAction.WORKSPACE_OWNERSHIP_GRANTED, target_type=AuditTarget.WORKSPACE,
            target_id=workspace.id,
            payload={"name": workspace.name, "slug": workspace.slug,
                     "notified": [str(owner) for owner in previous]},
        )  # fmt: skip
        await self._session.commit()
        return await self.workspace_detail(workspace.id)

    # --- Настройки ----------------------------------------------------------------

    async def settings(self) -> SettingsRead:
        return SettingsRead.model_validate(await self._instance.get())

    async def update_settings(self, ctx: AdminContext, data: SettingsUpdate) -> SettingsRead:
        current = await self._instance.get()
        changes: dict[str, dict[str, Any]] = {}
        for field in data.model_fields_set:
            new = getattr(data, field)
            old = getattr(current, field)
            if new != old:
                changes[field] = {"from": old, "to": new}
                setattr(current, field, new)
        if changes:
            current.updated_by = ctx.user_id
            current.updated_at = datetime.now(UTC)
            await self._record(
                ctx, AuditAction.SETTINGS_CHANGED, target_type=AuditTarget.SETTINGS,
                payload=changes,
            )  # fmt: skip
            await self._session.commit()
        return SettingsRead.model_validate(current)


def _workspace_key(sort: str) -> Callable[[AdminWorkspaceRow], tuple[Any, str]]:
    """Ключ сортировки списка пространств: крупные и недавние — первыми."""
    match sort:
        case "name":
            return lambda row: (row.name.lower(), str(row.id))
        case "members":
            return lambda row: (-row.members, str(row.id))
        case "tasks":
            return lambda row: (-row.tasks, str(row.id))
        case "activity":
            # Давно забытые — первыми: этот список ищет брошенное.
            return lambda row: (
                (row.last_activity_at or row.created_at).timestamp(),
                str(row.id),
            )
    return lambda row: (-row.created_at.timestamp(), str(row.id))


def _decode_key(sort: str, value: str, row_id: str) -> tuple[Any, str]:
    try:
        parsed: Any = value if sort == "name" else float(value)
    except ValueError as error:
        raise ApiError(400, "invalid_cursor", "Курсор повреждён или устарел") from error
    return parsed, row_id
