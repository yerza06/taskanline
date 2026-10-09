"""Приглашения в workspace, команду или проект.

`scope_id` — полиморфная ссылка без внешнего ключа: целостность держит сервис,
отзывая приглашения при удалении объекта. Сам токен в базе не хранится — только
SHA-256-хеш; токен уходит в письме и больше нигде.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CHAR, CheckConstraint, ForeignKey, Index, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.core.database import Base
from app.core.enums import InvitationScope, InvitationStatus


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint("scope_type IN ('workspace', 'team', 'project')", name="scope_type"),
        CheckConstraint("status IN ('pending', 'accepted', 'expired', 'revoked')", name="status"),
        # Роль обязана существовать на выбранном уровне; `owner` не приглашается —
        # владение только передаётся.
        CheckConstraint(
            "(scope_type = 'workspace' AND role IN ('admin', 'member', 'guest'))"
            " OR (scope_type = 'team' AND role IN ('lead', 'member'))"
            " OR (scope_type = 'project' AND role IN ('admin', 'member', 'viewer'))",
            name="role_matches_scope",
        ),
        Index("idx_invitations_token", "token_hash", unique=True),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    scope_type: Mapped[InvitationScope] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    invited_by: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[InvitationStatus] = mapped_column(
        String(16), nullable=False, server_default="pending", default=InvitationStatus.PENDING
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    accepted_by: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


# Одно действующее приглашение на адрес и объект; принятые и отозванные не мешают.
Index(
    "idx_invitations_pending",
    Invitation.workspace_id,
    func.lower(Invitation.email),
    Invitation.scope_type,
    Invitation.scope_id,
    unique=True,
    postgresql_where=text("status = 'pending'"),
)
