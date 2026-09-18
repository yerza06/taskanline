"""Запросы к таблицам сессий и токенов агента."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TokenScope
from app.modules.auth.models import ApiToken, RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        token: RefreshToken | None = await self._session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return token

    async def create(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip: str | None,
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def revoke(self, token: RefreshToken, *, at: datetime) -> None:
        token.revoked_at = at
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: UUID, *, at: datetime) -> None:
        """Полный сброс сессий: применяется при обнаружении компрометации."""
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=at)
        )
        await self._session.flush()


class ApiTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_hash(self, token_hash: str) -> ApiToken | None:
        token: ApiToken | None = await self._session.scalar(
            select(ApiToken).where(ApiToken.token_hash == token_hash)
        )
        return token

    async def touch_last_used(self, token_id: UUID, *, not_before: datetime) -> None:
        """Отметка об использовании — не чаще раза в минуту.

        Условие стоит в самом UPDATE, а не в Python: одновременные запросы агента
        иначе устраивают гонку и пишут метку по нескольку раз подряд.
        """
        await self._session.execute(
            update(ApiToken)
            .where(
                ApiToken.id == token_id,
                or_(ApiToken.last_used_at.is_(None), ApiToken.last_used_at < not_before),
            )
            .values(last_used_at=datetime.now(UTC))
        )

    async def list_active(self, user_id: UUID) -> Sequence[ApiToken]:
        result = await self._session.scalars(
            select(ApiToken)
            .where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None))
            .order_by(ApiToken.created_at.desc())
        )
        return result.all()

    async def get_owned(self, token_id: UUID, user_id: UUID) -> ApiToken | None:
        """Владелец — часть условия выборки, а не отдельная проверка после неё."""
        token: ApiToken | None = await self._session.scalar(
            select(ApiToken).where(
                ApiToken.id == token_id,
                ApiToken.user_id == user_id,
                ApiToken.revoked_at.is_(None),
            )
        )
        return token

    async def create(
        self,
        *,
        user_id: UUID,
        name: str,
        token_hash: str,
        prefix: str,
        scope: TokenScope,
        expires_at: datetime | None,
    ) -> ApiToken:
        token = ApiToken(
            user_id=user_id,
            name=name,
            token_hash=token_hash,
            prefix=prefix,
            scope=scope,
            expires_at=expires_at,
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def revoke(self, token: ApiToken, *, at: datetime) -> None:
        token.revoked_at = at
        await self._session.flush()
