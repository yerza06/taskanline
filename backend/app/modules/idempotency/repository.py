"""Запросы к idempotency_keys."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.idempotency.models import IdempotencyKey


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str, user_id: UUID) -> IdempotencyKey | None:
        found: IdempotencyKey | None = await self._session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.key == key, IdempotencyKey.user_id == user_id
            )
        )
        return found

    async def add(
        self,
        *,
        key: str,
        user_id: UUID,
        endpoint: str,
        request_hash: str,
        status: int,
        body: dict[str, Any],
    ) -> None:
        self._session.add(
            IdempotencyKey(
                key=key,
                user_id=user_id,
                endpoint=endpoint,
                request_hash=request_hash,
                response_status=status,
                response_body=body,
            )
        )
        await self._session.flush()

    async def delete_older_than(self, moment: datetime) -> int:
        result = await self._session.execute(
            delete(IdempotencyKey).where(IdempotencyKey.created_at < moment)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]
