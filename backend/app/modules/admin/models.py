"""Журнал административных действий — только добавление.

Отдельно от `activities`: та привязана к workspace и описывает работу над задачами,
эта — действия над самим сервером и его людьми. Записи не правятся и не удаляются
через API никем, включая superadmin.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import INET, JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.core.database import Base
from app.core.enums import AuditAction, AuditTarget


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"
    __table_args__ = (
        Index("idx_audit_created", text("created_at DESC")),
        Index("idx_audit_actor", "actor_id", text("created_at DESC")),
        Index("idx_audit_target", "target_type", "target_id", text("created_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # RESTRICT: актор не исчезает, пока о нём есть записи (удаление — анонимизация).
    actor_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[AuditAction] = mapped_column(String(48), nullable=False)
    target_type: Mapped[AuditTarget | None] = mapped_column(String(16))
    target_id: Mapped[UUID | None] = mapped_column(Uuid)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
