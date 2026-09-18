"""Таблица `users`.

Пользователь глобален, а не привязан к рабочему пространству: один человек
участвует в нескольких workspace под одним аккаунтом.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.core.database import Base
from app.core.enums import InstanceRole


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('superadmin', 'admin', 'support', 'user')", name="role"),
        Index("idx_users_email", "email", unique=True),
        # Частичный индекс: администраторов единицы, а строк в users — все.
        Index("idx_users_admins", "role", postgresql_where=text("role <> 'user'")),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    # Роль инстанса: что человек может делать с сервером. К ролям внутри
    # workspace отношения не имеет — это независимая ось.
    role: Mapped[InstanceRole] = mapped_column(
        String(16), nullable=False, server_default="user", default=InstanceRole.USER
    )
    # Деактивация вместо удаления: история изменений не должна ссылаться в пустоту.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
