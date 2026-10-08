"""Ответы на запросы с `Idempotency-Key`.

Таблица существует потому, что Redis в системе нет: агент, не дождавшийся ответа,
повторяет запрос и не должен получить дубликат задачи.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CHAR, ForeignKey, Index, SmallInteger, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (Index("idx_idempotency_gc", "created_at"),)

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    # Ключи разных пользователей не пересекаются.
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    response_status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
