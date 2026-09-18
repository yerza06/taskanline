"""Служебные таблицы аутентификации: `refresh_tokens` и `api_tokens`.

Обе хранят только SHA-256-хеш токена. Отличаются назначением: refresh-токен
принадлежит сессии человека и ротируется при каждом обновлении, PAT принадлежит
агенту, живёт долго и ограничен scope.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CHAR, CheckConstraint, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.core.database import Base
from app.core.enums import TokenScope


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("idx_refresh_tokens_hash", "token_hash", unique=True),
        Index("idx_refresh_tokens_user", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    # Заполняется при ротации и при отзыве всех сессий после компрометации.
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class ApiToken(Base):
    __tablename__ = "api_tokens"
    __table_args__ = (
        CheckConstraint("scope IN ('read', 'read_write')", name="scope"),
        Index("idx_api_tokens_hash", "token_hash", unique=True),
        Index("idx_api_tokens_user", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    # Начало токена для показа в списке: полный токен восстановить неоткуда.
    prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    scope: Mapped[TokenScope] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # Обновляется не чаще раза в минуту: точность до секунды тут никому не нужна,
    # а запись на каждый запрос агента — заметная нагрузка.
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
