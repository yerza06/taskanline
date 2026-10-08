"""Совместная работа: comments, comment_mentions, activities, notifications.

Revision ID: 0004_collab
Revises: 0003_tasks
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_collab"
down_revision: str | None = "0003_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVITY_TYPES = (
    "task_created",
    "title_changed",
    "description_changed",
    "state_changed",
    "assignee_changed",
    "priority_changed",
    "due_date_changed",
    "project_changed",
    "parent_changed",
    "label_added",
    "label_removed",
    "relation_added",
    "relation_removed",
    "commented",
    "task_moved",
    "task_deleted",
    "task_restored",
)


def _created_at() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "created_at",
        postgresql.TIMESTAMP(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKeyConstraint:
    referred = target.split(".")[0]
    return sa.ForeignKeyConstraint(
        [column], [target], name=f"fk_{table}_{column}_{referred}", ondelete=ondelete
    )


def upgrade() -> None:
    op.create_table(
        "comments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("author_token_id", sa.UUID(), nullable=True),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        _created_at(),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        _fk("comments", "workspace_id", "workspaces.id", "CASCADE"),
        _fk("comments", "task_id", "tasks.id", "CASCADE"),
        _fk("comments", "author_id", "users.id", "RESTRICT"),
        _fk("comments", "author_token_id", "api_tokens.id", "SET NULL"),
        _fk("comments", "parent_id", "comments.id", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comments")),
    )
    op.create_index(
        "idx_comments_task",
        "comments",
        ["task_id", "created_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "comment_mentions",
        sa.Column("comment_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        _fk("comment_mentions", "comment_id", "comments.id", "CASCADE"),
        _fk("comment_mentions", "user_id", "users.id", "CASCADE"),
        _fk("comment_mentions", "workspace_id", "workspaces.id", "CASCADE"),
        sa.PrimaryKeyConstraint("comment_id", "user_id", name=op.f("pk_comment_mentions")),
    )

    op.create_table(
        "activities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("actor_token_id", sa.UUID(), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "type IN ({})".format(", ".join(f"'{kind}'" for kind in ACTIVITY_TYPES)),
            name=op.f("ck_activities_type"),
        ),
        _fk("activities", "workspace_id", "workspaces.id", "CASCADE"),
        _fk("activities", "task_id", "tasks.id", "CASCADE"),
        _fk("activities", "project_id", "projects.id", "CASCADE"),
        _fk("activities", "actor_id", "users.id", "RESTRICT"),
        _fk("activities", "actor_token_id", "api_tokens.id", "SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activities")),
    )
    op.create_index("idx_activities_task", "activities", ["task_id", sa.text("created_at DESC")])
    op.create_index("idx_activities_ws", "activities", ["workspace_id", sa.text("created_at DESC")])

    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("comment_id", sa.UUID(), nullable=True),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("read_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        _created_at(),
        sa.CheckConstraint(
            "type IN ('mentioned', 'assigned', 'commented', 'state_changed')",
            name=op.f("ck_notifications_type"),
        ),
        _fk("notifications", "workspace_id", "workspaces.id", "CASCADE"),
        _fk("notifications", "user_id", "users.id", "CASCADE"),
        _fk("notifications", "task_id", "tasks.id", "CASCADE"),
        _fk("notifications", "comment_id", "comments.id", "CASCADE"),
        _fk("notifications", "actor_id", "users.id", "CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        "idx_notifications_inbox",
        "notifications",
        ["user_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("read_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("activities")
    op.drop_table("comment_mentions")
    op.drop_table("comments")
