"""Политика cookie сессии в одном месте.

Четыре эндпоинта ставят и чистят одни и те же две cookie. Держать эти детали в
роутере значит размазать политику по четырём местам и однажды забыть флаг.
"""

from fastapi import Response

from app.core.config import get_settings


def set_session_cookies(response: Response, *, access: str, refresh: str) -> None:
    settings = get_settings()
    domain = settings.auth.cookie_domain or None
    response.set_cookie(
        settings.auth.access_cookie_name,
        access,
        max_age=settings.auth.access_ttl_minutes * 60,
        httponly=True,
        secure=settings.auth.cookie_secure,
        samesite=settings.auth.cookie_samesite,
        domain=domain,
        path="/",
    )
    response.set_cookie(
        settings.auth.refresh_cookie_name,
        refresh,
        max_age=settings.auth.refresh_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth.cookie_secure,
        samesite=settings.auth.cookie_samesite,
        domain=domain,
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    domain = settings.auth.cookie_domain or None
    for name in (settings.auth.access_cookie_name, settings.auth.refresh_cookie_name):
        response.delete_cookie(
            name,
            httponly=True,
            secure=settings.auth.cookie_secure,
            samesite=settings.auth.cookie_samesite,
            domain=domain,
            path="/",
        )
    clear_reauth_cookie(response)


# Подтверждение паролем нужно только разделу админки — туда и ограничен путь cookie.
REAUTH_COOKIE = "tkl_reauth"
REAUTH_PATH = "/api/v1/admin"


def set_reauth_cookie(response: Response, token: str, *, max_age: int) -> None:
    settings = get_settings()
    response.set_cookie(
        REAUTH_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.auth.cookie_secure,
        # Strict: опасное действие не должно подтверждаться переходом с чужого сайта.
        samesite="strict",
        domain=settings.auth.cookie_domain or None,
        path=REAUTH_PATH,
    )


def clear_reauth_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        REAUTH_COOKIE,
        httponly=True,
        secure=settings.auth.cookie_secure,
        samesite="strict",
        domain=settings.auth.cookie_domain or None,
        path=REAUTH_PATH,
    )
