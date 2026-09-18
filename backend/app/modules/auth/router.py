"""HTTP-слой аутентификации: разбор запроса, cookie, вызов сервиса.

Бизнес-правил здесь нет — только перевод между HTTP и сервисом.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.principal import CurrentPrincipal, WritePrincipal
from app.core.rate_limit import rate_limit
from app.modules.auth.cookies import clear_session_cookies, set_session_cookies
from app.modules.auth.schemas import (
    SessionResponse,
    TokenCreate,
    TokenCreated,
    TokenList,
    TokenRead,
)
from app.modules.auth.service import AuthService
from app.modules.auth.token_service import ApiTokenService
from app.modules.users.schemas import LoginRequest, RegisterRequest, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _login_limit() -> tuple[int, int]:
    settings = get_settings()
    return settings.auth.login_attempts, settings.auth.login_window_seconds


def _register_limit() -> tuple[int, int]:
    settings = get_settings()
    return settings.auth.register_attempts, settings.auth.register_window_seconds


def get_auth_service(session: Annotated[AsyncSession, Depends(get_session)]) -> AuthService:
    return AuthService(session)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


@router.post(
    "/register",
    response_model=SessionResponse,
    status_code=201,
    dependencies=[Depends(rate_limit("register", _register_limit))],
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse:
    """Регистрация сразу открывает сессию: отдельный вход после неё — лишний шаг."""
    user, tokens = await service.register(
        payload,
        user_agent=request.headers.get("user-agent"),
        ip=_client_ip(request),
    )
    set_session_cookies(response, access=tokens.access, refresh=tokens.refresh)
    return SessionResponse(user=UserRead.model_validate(user))


@router.post(
    "/login",
    response_model=SessionResponse,
    dependencies=[Depends(rate_limit("login", _login_limit))],
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse:
    user, tokens = await service.login(
        payload,
        user_agent=request.headers.get("user-agent"),
        ip=_client_ip(request),
    )
    set_session_cookies(response, access=tokens.access, refresh=tokens.refresh)
    return SessionResponse(user=UserRead.model_validate(user))


@router.post("/refresh", response_model=SessionResponse)
async def refresh(
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> SessionResponse:
    settings = get_settings()
    user, tokens = await service.refresh(
        request.cookies.get(settings.auth.refresh_cookie_name),
        user_agent=request.headers.get("user-agent"),
        ip=_client_ip(request),
    )
    set_session_cookies(response, access=tokens.access, refresh=tokens.refresh)
    return SessionResponse(user=UserRead.model_validate(user))


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    settings = get_settings()
    await service.logout(request.cookies.get(settings.auth.refresh_cookie_name))
    clear_session_cookies(response)


# Путь начинается с /me, но таблица и правила живут в модуле auth — роутер тоже.
tokens_router = APIRouter(prefix="/me/tokens", tags=["tokens"])


def get_token_service(session: Annotated[AsyncSession, Depends(get_session)]) -> ApiTokenService:
    return ApiTokenService(session)


@tokens_router.get("", response_model=TokenList)
async def list_tokens(
    principal: CurrentPrincipal,
    service: Annotated[ApiTokenService, Depends(get_token_service)],
) -> TokenList:
    tokens = await service.list_for(principal.user_id)
    return TokenList(items=[TokenRead.model_validate(token) for token in tokens])


@tokens_router.post("", response_model=TokenCreated, status_code=201)
async def create_token(
    payload: TokenCreate,
    principal: WritePrincipal,
    service: Annotated[ApiTokenService, Depends(get_token_service)],
) -> TokenCreated:
    """Полное значение токена показывается ровно здесь и больше нигде."""
    token, raw = await service.issue(principal.user_id, payload)
    return TokenCreated(**TokenRead.model_validate(token).model_dump(), token=raw)


@tokens_router.delete("/{token_id}", status_code=204)
async def revoke_token(
    token_id: UUID,
    principal: WritePrincipal,
    service: Annotated[ApiTokenService, Depends(get_token_service)],
) -> None:
    await service.revoke(token_id, principal.user_id)
