"""Views: сохранённые срезы задач.

Revision ID: 0005_views
Revises: 0004_collab
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_views"
down_revision: str | None = "0004_collab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "views",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("team_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("group_by", sa.String(length=24), nullable=True),
        sa.Column("sort_by", sa.String(length=24), server_default="manual", nullable=False),
        sa.Column("sort_direction", sa.String(length=4), server_default="asc", nullable=False),
        sa.Column("layout", sa.String(length=16), server_default="list", nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        # Владелец и команда заполнены ровно тогда, когда того требует scope.
        sa.CheckConstraint(
            "(scope = 'user' AND owner_id IS NOT NULL AND team_id IS NULL)"
            " OR (scope = 'team' AND team_id IS NOT NULL AND owner_id IS NULL)"
            " OR (scope = 'workspace' AND team_id IS NULL AND owner_id IS NULL)",
            name=op.f("ck_views_view_scope"),
        ),
        sa.CheckConstraint(
            "group_by IS NULL OR group_by IN"
            " ('state', 'assignee', 'priority', 'project', 'label', 'due_date')",
            name=op.f("ck_views_group_by"),
        ),
        sa.CheckConstraint(
            "sort_by IN ('manual', 'priority', 'due_date', 'created_at', 'updated_at', 'title')",
            name=op.f("ck_views_sort_by"),
        ),
        sa.CheckConstraint("sort_direction IN ('asc', 'desc')", name=op.f("ck_views_sort_direction")),
        sa.CheckConstraint("layout IN ('list', 'board')", name=op.f("ck_views_layout")),
        sa.CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9a-fA-F]{6}$'", name=op.f("ck_views_color_format")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_views_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_views_owner_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_views_team_id_teams"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_views_created_by_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_views")),
    )
    op.create_index(
        "idx_views_user", "views", ["owner_id", "position"], postgresql_where=sa.text("scope = 'user'")
    )
    op.create_index(
        "idx_views_team", "views", ["team_id", "position"], postgresql_where=sa.text("scope = 'team'")
    )
    op.create_index(
        "idx_views_workspace",
        "views",
        ["workspace_id", "position"],
        postgresql_where=sa.text("scope = 'workspace'"),
    )


def downgrade() -> None:
    op.drop_table("views")
