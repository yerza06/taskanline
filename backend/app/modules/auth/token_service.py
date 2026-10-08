"""Токены агента: выпуск, проверка и отзыв.

Отдельно от `service.py` с сессиями человека: у токена другой жизненный цикл —
он живёт долго, ограничен scope и не ротируется.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.security import generate_pat, hash_token, token_prefix
from app.modules.auth.models import ApiToken
from app.modules.auth.repository import ApiTokenRepository
from app.modules.auth.schemas import TokenCreate

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

    async def list_for(self, user_id: UUID) -> Sequence[ApiToken]:
        return await self._tokens.list_active(user_id)

    async def issue(self, user_id: UUID, data: TokenCreate) -> tuple[ApiToken, str]:
        """Возвращает запись и полный токен. Показать его можно только сейчас."""
        raw = generate_pat()
        token = await self._tokens.create(
            user_id=user_id,
            name=data.name,
            token_hash=hash_token(raw),
            prefix=token_prefix(raw),
            scope=data.scope,
            expires_at=data.expires_at,
        )
        await self._session.commit()
        return token, raw

    async def revoke(self, token_id: UUID, user_id: UUID) -> None:
        token = await self._tokens.get_owned(token_id, user_id)
        # Чужой токен отвечает 404, а не 403: иначе перебором идентификаторов
        # выясняется, какие токены существуют у других.
        if token is None:
            raise ApiError(404, "token_not_found", "Токен не найден")

        await self._tokens.revoke(token, at=datetime.now(UTC))
        await self._session.commit()

    # --- Для админ-панели: без commit, права проверяет вызывающий -----------------

    async def list_all(self, user_id: UUID) -> Sequence[ApiToken]:
        return await self._tokens.list_all(user_id)

    async def revoke_all(self, user_id: UUID) -> None:
        await self._tokens.revoke_all_for_user(user_id, at=datetime.now(UTC))

    async def revoke_for(self, token_id: UUID, user_id: UUID) -> ApiToken:
        token = await self._tokens.get_owned(token_id, user_id)
        if token is None:
            raise ApiError(404, "token_not_found", "Токен не найден")
        if token.revoked_at is None:
            await self._tokens.revoke(token, at=datetime.now(UTC))
        return token
