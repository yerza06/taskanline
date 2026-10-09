"""Идемпотентность создания: повтор с тем же `Idempotency-Key` получает сохранённый ответ.

Ответ сохраняется в той же транзакции, что и созданный объект: либо есть оба, либо
ни одного. Два одновременных запроса с одним ключом сталкиваются на первичном ключе
таблицы; проигравший откатывает свою работу целиком и отдаёт ответ победителя.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.idempotency.repository import IdempotencyRepository

# Сколько живёт сохранённый ответ.
RETENTION = timedelta(hours=24)
MAX_KEY_LENGTH = 255


@dataclass(frozen=True)
class Outcome:
    status: int
    body: dict[str, Any]
    replayed: bool


def request_hash(request: Any) -> str:
    """SHA-256 канонического JSON: порядок ключей и пробелы не делают запрос другим."""
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _reuse() -> ApiError:
    return ApiError(
        409,
        "idempotency_key_reuse",
        "Этот Idempotency-Key уже использован для другого запроса",
    )


class IdempotencyService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._keys = IdempotencyRepository(session)

    async def execute(
        self,
        *,
        user_id: UUID,
        key: str | None,
        endpoint: str,
        request: Any,
        produce: Callable[[], Awaitable[tuple[int, dict[str, Any]]]],
    ) -> Outcome:
        """Выполнить `produce` и закоммитить; с ключом — один раз на ключ."""
        if key is None:
            status, body = await produce()
            await self._session.commit()
            return Outcome(status, body, replayed=False)

        if not key or len(key) > MAX_KEY_LENGTH or not key.isprintable():
            raise ApiError(
                400,
                "invalid_idempotency_key",
                f"Idempotency-Key — от 1 до {MAX_KEY_LENGTH} печатных символов",
            )
        digest = request_hash(request)
        stored = await self._replay(user_id, key, endpoint, digest)
        if stored is not None:
            return stored

        status, body = await produce()
        try:
            await self._keys.add(
                key=key,
                user_id=user_id,
                endpoint=endpoint,
                request_hash=digest,
                status=status,
                body=body,
            )
            await self._session.commit()
        except IntegrityError:
            # Параллельный запрос с тем же ключом успел первым: наша работа
            # откатывается целиком, ответ — его.
            await self._session.rollback()
            stored = await self._replay(user_id, key, endpoint, digest)
            if stored is None:
                raise
            return stored
        return Outcome(status, body, replayed=False)

    async def purge_expired(self, now: datetime | None = None) -> int:
        """Удалить ответы старше суток. Вызывается при старте и раз в час."""
        removed = await self._keys.delete_older_than((now or datetime.now(UTC)) - RETENTION)
        await self._session.commit()
        return removed

    async def _replay(self, user_id: UUID, key: str, endpoint: str, digest: str) -> Outcome | None:
        stored = await self._keys.get(key, user_id)
        if stored is None:
            return None
        if stored.endpoint != endpoint or stored.request_hash != digest:
            raise _reuse()
        return Outcome(stored.response_status, stored.response_body, replayed=True)
