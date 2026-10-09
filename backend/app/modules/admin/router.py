"""HTTP-слой раздела администрирования: `/api/v1/admin/*`.

Каждый маршрут защищён `require_instance_role` — порядок отказов и запрет PAT описаны
в `core/admin_access.py`. Опасные действия дополнительно требуют свежего
подтверждения паролем (`reauth=True`).
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_access import AdminContext, require_instance_role
from app.core.database import get_session
from app.core.enums import AuditAction, AuditTarget, InstanceRole
from app.core.errors import ApiError, error_response
from app.core.mail import Mailer, get_mailer, send_safely
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.core.security import REAUTH_TTL
from app.modules.admin.schemas import (
    AdminSession,
    AdminUserDetail,
    AdminUserPage,
    AdminUserRow,
    AdminWorkspaceDetail,
    AdminWorkspacePage,
    AuditFilters,
    AuditPage,
    ReauthRequest,
    RoleChange,
    SettingsRead,
    SettingsUpdate,
    Stats,
)
from app.modules.admin.service import WORKSPACE_SORTS, AdminService
from app.modules.auth.cookies import clear_session_cookies, set_reauth_cookie

router = APIRouter(prefix="/admin", tags=["admin"])

Support = Annotated[AdminContext, Depends(require_instance_role(InstanceRole.SUPPORT))]
Admin = Annotated[AdminContext, Depends(require_instance_role(InstanceRole.ADMIN))]
AdminReauth = Annotated[
    AdminContext, Depends(require_instance_role(InstanceRole.ADMIN, reauth=True))
]
SuperReauth = Annotated[
    AdminContext, Depends(require_instance_role(InstanceRole.SUPERADMIN, reauth=True))
]
Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]


def get_admin_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> AdminService:
    return AdminService(session, request.app.state.reauth_failures)


Service = Annotated[AdminService, Depends(get_admin_service)]


# --- Сессия -------------------------------------------------------------------------


@router.get("/session", response_model=AdminSession)
async def read_session(ctx: Support, service: Service) -> AdminSession:
    """Кто вошёл, с какой ролью и до какого момента подтверждён паролем."""
    return await service.session_info(ctx)


@router.post("/session", response_model=AdminSession)
async def open_session(ctx: Support, service: Service) -> AdminSession:
    """Вход в админку: приложение вызывает его при открытии — `admin_login` в журнал."""
    return await service.open_session(ctx)


@router.post("/reauth", response_model=AdminSession)
async def reauth(
    payload: ReauthRequest, ctx: Support, service: Service, response: Response
) -> AdminSession | JSONResponse:
    """Повторный ввод пароля: открывает окно опасных действий на 15 минут."""
    try:
        session, token = await service.reauth(ctx, payload.password)
    except ApiError as error:
        if error.code != "session_terminated":
            raise
        # Третья неудача: сессия закрыта на сервере — и cookie уходят из браузера.
        terminated = error_response(error.status_code, error.code, error.message, error.details)
        clear_session_cookies(terminated)
        return terminated
    set_reauth_cookie(response, token, max_age=int(REAUTH_TTL.total_seconds()))
    return session


# --- Дашборд и журнал ---------------------------------------------------------------


@router.get("/stats", response_model=Stats)
async def stats(_: Support, service: Service) -> Stats:
    return await service.stats()


@router.get("/audit", response_model=AuditPage)
async def audit(
    _: Support,
    service: Service,
    actor_id: UUID | None = None,
    action: AuditAction | None = None,
    target_type: AuditTarget | None = None,
    target_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> AuditPage:
    filters = AuditFilters(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        date_from=date_from,
        date_to=date_to,
    )
    return await service.audit_page(filters, cursor=cursor, limit=limit)


# --- Пользователи -------------------------------------------------------------------


@router.get("/users", response_model=AdminUserPage)
async def list_users(
    _: Support,
    service: Service,
    q: Annotated[str | None, Query(max_length=200, description="Email или имя")] = None,
    role: InstanceRole | None = None,
    status: Annotated[str | None, Query(pattern="^(active|blocked|deleted)$")] = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> AdminUserPage:
    return await service.users_page(
        query=q.strip() if q and q.strip() else None,
        role=role,
        status=status,
        cursor=cursor,
        limit=limit,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def read_user(user_id: UUID, _: Support, service: Service) -> AdminUserDetail:
    """Профиль, членства, токены агентов и последние 20 входов."""
    return await service.user_detail(user_id)


@router.post("/users/{user_id}/block", response_model=AdminUserRow)
async def block_user(user_id: UUID, ctx: Admin, service: Service) -> AdminUserRow:
    """Блокировка сразу гасит все сессии и все токены агентов пользователя."""
    return await service.block(ctx, user_id)


@router.post("/users/{user_id}/unblock", response_model=AdminUserRow)
async def unblock_user(user_id: UUID, ctx: Admin, service: Service) -> AdminUserRow:
    return await service.unblock(ctx, user_id)


@router.post("/users/{user_id}/reset-password", status_code=204)
async def reset_password(
    user_id: UUID,
    ctx: Admin,
    service: Service,
    background: BackgroundTasks,
    mailer: Annotated[Mailer, Depends(get_mailer)],
) -> None:
    """Письмо со ссылкой на смену пароля. Администратор пароль не видит и не задаёт."""
    message = await service.reset_password(ctx, user_id)
    background.add_task(send_safely, mailer, message)


@router.delete("/users/{user_id}/tokens/{token_id}", status_code=204)
async def revoke_user_token(user_id: UUID, token_id: UUID, ctx: Admin, service: Service) -> None:
    await service.revoke_token(ctx, user_id, token_id)


@router.patch("/users/{user_id}/role", response_model=AdminUserRow)
async def change_role(
    user_id: UUID, payload: RoleChange, ctx: SuperReauth, service: Service
) -> AdminUserRow:
    return await service.change_role(ctx, user_id, payload.role)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: UUID, ctx: SuperReauth, service: Service) -> None:
    """Анонимизация: задачи и комментарии остаются, автор становится заглушкой."""
    await service.delete_user(ctx, user_id)


# --- Рабочие пространства -----------------------------------------------------------


@router.get("/workspaces", response_model=AdminWorkspacePage)
async def list_workspaces(
    _: Support,
    service: Service,
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort: Annotated[
        str, Query(description="created, name, members, tasks, activity (давние первыми)")
    ] = "created",
    limit: Limit = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> AdminWorkspacePage:
    if sort not in WORKSPACE_SORTS:
        raise ApiError(400, "invalid_sort", "Неизвестная сортировка", {"allowed": WORKSPACE_SORTS})
    return await service.workspaces_page(
        query=q.strip() if q and q.strip() else None, sort=sort, cursor=cursor, limit=limit
    )


@router.get("/workspaces/{workspace_id}", response_model=AdminWorkspaceDetail)
async def read_workspace(workspace_id: UUID, _: Support, service: Service) -> AdminWorkspaceDetail:
    return await service.workspace_detail(workspace_id)


@router.delete("/workspaces/{workspace_id}", status_code=204)
async def delete_workspace(workspace_id: UUID, ctx: AdminReauth, service: Service) -> None:
    await service.delete_workspace(ctx, workspace_id)


@router.post("/workspaces/{workspace_id}/grant-ownership", response_model=AdminWorkspaceDetail)
async def grant_ownership(
    workspace_id: UUID, ctx: SuperReauth, service: Service
) -> AdminWorkspaceDetail:
    """Назначить себя владельцем — с записью в журнал и уведомлением владельцам."""
    return await service.grant_ownership(ctx, workspace_id)


# --- Настройки ----------------------------------------------------------------------


@router.get("/settings", response_model=SettingsRead)
async def read_settings(_: Support, service: Service) -> SettingsRead:
    return await service.settings()


@router.patch("/settings", response_model=SettingsRead)
async def update_settings(
    payload: SettingsUpdate, ctx: SuperReauth, service: Service
) -> SettingsRead:
    return await service.update_settings(ctx, payload)
