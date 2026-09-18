"""Токены агента: выпуск, проверка и отзыв.

Отдельно от `service.py` с сессиями человека: у токена другой жизненный цикл —
он живёт долго, ограничен scope и не ротируется.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.auth.models import ApiToken
from app.modules.auth.repository import ApiTokenRepository

# Чаще раза в минуту отметку писать незачем: точность до секунды никому не нужна,
# а запись на каждый запрос агента — заметная нагрузка на базу.
LAST_USED_INTERVAL = timedelta(minutes=1)


class ApiTokenService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tokens = ApiTokenRepository(session)

    async def resolve(self, token_hash: str) -> ApiToken:
        """Действующий токен по хешу либо `ApiError(401)`."""
        token = await self._tokens.get_by_hash(token_hash)
        now = datetime.now(UTC)
        expired = token is not None and token.expires_at is not None and token.expires_at <= now
        if token is None or token.revoked_at is not None or expired:
            raise ApiError(401, "invalid_token", "Токен недействителен")

        await self._tokens.touch_last_used(token.id, not_before=now - LAST_USED_INTERVAL)
        await self._session.commit()
        return token
