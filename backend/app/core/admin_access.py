"""Доступ к разделу администрирования инстанса — отдельно от `core/permissions.py`.

Права внутри workspace и права над сервером — две независимые оси, и проверяются
они разными зависимостями. Порядок отказов фиксирован (админ-спека §5):

1. нет аутентификации — 401;
2. роль `user` — 404 на любой путь раздела: обычный пользователь не узнаёт, что он есть;
3. токен агента (PAT) — `403 session_required`, при любом scope и любой роли;
4. роль ниже нужной — `403 insufficient_role`;
5. опасное действие без свежего подтверждения паролем — `403 reauth_required`.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import Request

from app.core.enums import AuthMethod, InstanceRole
from app.core.errors import ApiError
from app.core.principal import CurrentPrincipal, Principal
from app.core.security import reauth_expiry

RANK: dict[InstanceRole, int] = {
    InstanceRole.USER: 0,
    InstanceRole.SUPPORT: 1,
    InstanceRole.ADMIN: 2,
    InstanceRole.SUPERADMIN: 3,
}


@dataclass(frozen=True)
class AdminContext:
    principal: Principal
    ip: str | None
    user_agent: str | None
    # До какого момента действует подтверждение паролем; `None` — не подтверждено.
    reauth_until: datetime | None

    @property
    def user_id(self) -> UUID:
        return self.principal.user_id

    @property
    def role(self) -> InstanceRole:
        return self.principal.instance_role


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Не найдено")


def require_instance_role(
    minimum: InstanceRole, *, reauth: bool = False
) -> Callable[..., Awaitable[AdminContext]]:
    """Зависимость эндпоинта раздела: минимальная роль инстанса и, для опасных
    действий, свежее подтверждение паролем."""

    async def dependency(request: Request, principal: CurrentPrincipal) -> AdminContext:
        from app.modules.auth.cookies import REAUTH_COOKIE

        if principal.instance_role == InstanceRole.USER:
            raise not_found()
        if principal.auth_method != AuthMethod.SESSION:
            raise ApiError(
                403,
                "session_required",
                "Админ-панель принимает только сессию человека — токены агентов сюда не пускают",
            )
        if RANK[principal.instance_role] < RANK[minimum]:
            raise ApiError(
                403,
                "insufficient_role",
                "Недостаточно прав для этого действия",
                {"required": minimum.value},
            )
        until = reauth_expiry(request.cookies.get(REAUTH_COOKIE), principal.user_id)
        if reauth and until is None:
            raise ApiError(
                403, "reauth_required", "Подтвердите действие паролем: POST /admin/reauth"
            )
        return AdminContext(
            principal=principal,
            ip=request.client.host if request.client is not None else None,
            user_agent=request.headers.get("user-agent"),
            reauth_until=until,
        )

    return dependency
