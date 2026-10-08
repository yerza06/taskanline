"""`Principal` — единая абстракция поверх двух способов доказать, кто ты.

Человек приходит с cookie-сессией, агент — с токеном в `Authorization: Bearer`.
Дальше по коду разницы между ними нет: авторизация написана один раз и смотрит
на `Principal`, а не на то, откуда он взялся.
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.enums import AuthMethod, InstanceRole, TokenScope
from app.core.errors import ApiError
from app.core.security import PAT_PREFIX, decode_access_token, hash_token

READ = "read"
WRITE = "write"

_SCOPES: dict[TokenScope, frozenset[str]] = {
    TokenScope.READ: frozenset({READ}),
    TokenScope.READ_WRITE: frozenset({READ, WRITE}),
}


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    instance_role: InstanceRole
    scopes: frozenset[str]
    auth_method: AuthMethod
    # Заполнен только у агента. Попадёт в activities, чтобы в истории задачи было
    # видно, что изменение сделал агент, а не человек за клавиатурой.
    token_id: UUID | None


def _invalid_token() -> ApiError:
    """Причина отказа наружу не уточняется: подробности помогают подбирающему."""
    return ApiError(401, "invalid_token", "Токен недействителен")


async def get_principal(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> Principal:
    """Токен агента проверяется раньше cookie.

    Если в окружении случайно остались обе формы, агент должен действовать своим
    токеном и своим scope — иначе ограничение `scope = read` обходится случайной
    сессией в том же браузере.
    """
    # Импорты внутри функции: модули зависят от core, и обратная связь на уровне
    # модуля замкнула бы импорт в кольцо.
    from app.modules.auth.token_service import ApiTokenService
    from app.modules.instance.service import InstanceService
    from app.modules.users.service import UserService

    header = request.headers.get("authorization")
    if header:
        scheme, _, raw_token = header.partition(" ")
        if scheme.lower() != "bearer" or not raw_token.startswith(PAT_PREFIX):
            raise _invalid_token()
        token = await ApiTokenService(session).resolve(hash_token(raw_token))
        user = await UserService(session).get_active(token.user_id)
        await InstanceService(session).check_maintenance(user.role)
        return Principal(
            user_id=user.id,
            instance_role=user.role,
            scopes=_SCOPES[TokenScope(token.scope)],
            auth_method=AuthMethod.TOKEN,
            token_id=token.id,
        )

    from app.core.config import get_settings

    cookie = request.cookies.get(get_settings().auth.access_cookie_name)
    if not cookie:
        raise ApiError(401, "unauthorized", "Требуется аутентификация")

    user_id = decode_access_token(cookie)
    user = await UserService(session).get_active(user_id)
    await InstanceService(session).check_maintenance(user.role)
    # У человека в браузере scope не ограничивается: ограничивать сессию нечем и незачем.
    return Principal(
        user_id=user.id,
        instance_role=user.role,
        scopes=frozenset({READ, WRITE}),
        auth_method=AuthMethod.SESSION,
        token_id=None,
    )


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_write(principal: CurrentPrincipal) -> Principal:
    """Мутирующий эндпоинт. Токен на чтение сюда не проходит ни при какой роли."""
    if WRITE not in principal.scopes:
        raise ApiError(403, "insufficient_scope", "Токен выдан только на чтение")
    return principal


WritePrincipal = Annotated[Principal, Depends(require_write)]


async def get_optional_principal(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> Principal | None:
    """Для эндпоинтов, открытых и анониму.

    Нет учётных данных — аноним. Есть, но негодные — 401, а не аноним: иначе
    клиент с протухшим access-токеном не узнает, что пора обновить сессию, и
    человека с учётной записью попросят зарегистрироваться заново.
    """
    # Импорт внутри функции по той же причине, что и выше — против кольца импортов.
    from app.core.config import get_settings

    settings = get_settings()
    has_credentials = request.headers.get("authorization") or any(
        name in request.cookies
        for name in (settings.auth.access_cookie_name, settings.auth.refresh_cookie_name)
    )
    if not has_credentials:
        return None
    return await get_principal(request, session)


OptionalPrincipal = Annotated[Principal | None, Depends(get_optional_principal)]
