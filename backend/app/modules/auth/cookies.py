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
