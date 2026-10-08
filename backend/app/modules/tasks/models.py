"""Задачи и связи между ними."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.core.database import Base
from app.core.enums import RelationType


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        # 0 — без приоритета, 1 — срочный … 4 — низкий.
        CheckConstraint("priority BETWEEN 0 AND 4", name="priority"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 500", name="title_length"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="no_self_parent"),
        Index("idx_tasks_key", "team_id", "number", unique=True),
        # Основной индекс списков: доска и список задач команды.
        Index(
            "idx_tasks_board",
            "workspace_id",
            "team_id",
            "state_id",
            "sort_order",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_tasks_assignee",
            "workspace_id",
            "assignee_id",
            "state_id",
            postgresql_where=text("deleted_at IS NULL AND assignee_id IS NOT NULL"),
        ),
        Index(
            "idx_tasks_project",
            "workspace_id",
            "project_id",
            "sort_order",
            postgresql_where=text("deleted_at IS NULL AND project_id IS NOT NULL"),
        ),
        Index("idx_tasks_parent", "parent_id", postgresql_where=text("parent_id IS NOT NULL")),
        Index(
            "idx_tasks_due",
            "workspace_id",
            "due_date",
            postgresql_where=text("deleted_at IS NULL AND due_date IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    # Команда задаёт префикс ключа: ENG-142.
    team_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL")
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    state_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workflow_states.id", ondelete="RESTRICT"), nullable=False
    )
    assignee_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    creator_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    priority: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0"), default=0
    )
    due_date: Mapped[date | None] = mapped_column(Date)
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL")
    )
    # Дробный индекс. Сравнение побайтовое: алфавит base62 упорядочен по ASCII,
    # а лингвистическая коллация поставила бы `a` перед `B`.
    sort_order: Mapped[str] = mapped_column(Text(collation="C"), nullable=False)
    # Зарезервировано под циклы и оценки: API не отдаёт и не принимает.
    estimate: Mapped[int | None] = mapped_column(SmallInteger)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


def search_document() -> Any:
    """Выражение полнотекстового поиска — дословно то же, что в `idx_tasks_search`.

    Константы — литералы SQL, а не параметры: с `$1` вместо `'simple'` выражение
    запроса перестаёт совпадать с выражением индекса, и планировщик его не берёт.
    """
    return func.to_tsvector(
        literal_column("'simple'"),
        Task.title.op("||")(literal_column("' '")).op("||")(
            func.coalesce(Task.description, literal_column("''"))
        ),
    )


# Таблица указывается явно: первым в выражении стоит литерал, и сам индекс
# свою таблицу по нему не находит — метаданные и миграции бы разошлись.
Index("idx_tasks_search", search_document(), postgresql_using="gin", _table=Task.__table__)  # type: ignore[arg-type]


class TaskRelation(Base):
    """Хранится одно направление: `blocked_by` — это `blocks`, прочитанный с другого конца."""

    __tablename__ = "task_relations"
    __table_args__ = (
        CheckConstraint("type IN ('blocks', 'relates_to', 'duplicates')", name="type"),
        CheckConstraint("source_task_id <> target_task_id", name="no_self"),
        Index("idx_relations_unique", "source_task_id", "target_task_id", "type", unique=True),
        Index("idx_relations_target", "target_task_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    source_task_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    target_task_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[RelationType] = mapped_column(String(16), nullable=False)
    created_by: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
