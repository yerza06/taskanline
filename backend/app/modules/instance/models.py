"""Политика инстанса — единственная строка `instance_settings`.

Секреты здесь не лежат никогда: они в переменных окружения. Здесь — то, что
администратор меняет из админки без перезапуска и без доступа к серверу.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import RegistrationMode

SETTINGS_ID = 1


class InstanceSettings(Base):
    __tablename__ = "instance_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint(
            "registration_mode IN ('invite_only', 'open', 'domain_allowlist')",
            name="registration_mode",
        ),
        CheckConstraint("invitation_ttl_days BETWEEN 1 AND 365", name="invitation_ttl"),
    )

    id: Mapped[int] = mapped_column(
        SmallInteger, primary_key=True, autoincrement=False, default=SETTINGS_ID
    )
    instance_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="TasKanLine")
    registration_mode: Mapped[RegistrationMode] = mapped_column(
        String(16), nullable=False, server_default="invite_only"
    )
    allowed_email_domains: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    invitation_ttl_days: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="7"
    )
    maintenance_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
