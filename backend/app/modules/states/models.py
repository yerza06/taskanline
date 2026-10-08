"""Workflow-статусы команды."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.core.database import Base
from app.core.enums import StateType


class WorkflowState(Base):
    """Статус настраивается командой, но его тип — из фиксированного набора."""

    __tablename__ = "workflow_states"
    __table_args__ = (
        CheckConstraint(
            "type IN ('backlog', 'unstarted', 'started', 'completed', 'canceled')", name="type"
        ),
        CheckConstraint("color ~ '^#[0-9a-fA-F]{6}$'", name="color_format"),
        # Статус по умолчанию у команды ровно один — это держит сама база.
        Index("idx_states_default", "team_id", unique=True, postgresql_where=text("is_default")),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[StateType] = mapped_column(String(16), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    # Порядок колонок доски.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


Index("idx_states_name", WorkflowState.team_id, func.lower(WorkflowState.name), unique=True)
