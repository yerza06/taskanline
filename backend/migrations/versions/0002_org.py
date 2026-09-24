"""Организационная структура: workspaces, teams, projects, членства, приглашения.

Членства в командах и проектах ссылаются на workspace_members составным ключом
(workspace_id, user_id): без членства в пространстве вложенного не бывает, и
исключение из пространства снимает всё вложенное каскадом.

Revision ID: 0002_org
Revises: 0001_users_auth
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_org"
down_revision: str | None = "0001_users_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps(*, updated: bool = True) -> list[sa.Column]:  # type: ignore[type-arg]
    columns = [
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        )
    ]
    if updated:
        columns.append(
            sa.Column(
                "updated_at",
                postgresql.TIMESTAMP(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            )
        )
    return columns


def _membership_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id", "user_id"],
        ["workspace_members.workspace_id", "workspace_members.user_id"],
        name=f"fk_{table}_workspace_member",
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", postgresql.CITEXT(), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_workspaces_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
    )
    op.create_index("idx_workspaces_slug", "workspaces", ["slug"], unique=True)

    op.create_table(
        "workspace_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        *_timestamps(updated=False),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'guest')", name=op.f("ck_workspace_members_role")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_workspace_members_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_workspace_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_members")),
    )
    op.create_index(
        "idx_ws_members_unique", "workspace_members", ["workspace_id", "user_id"], unique=True
    )
    op.create_index("idx_ws_members_user", "workspace_members", ["user_id"])

    op.create_table(
        "teams",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_private", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("task_counter", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("key ~ '^[A-Z]{2,5}$'", name=op.f("ck_teams_key_format")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_teams_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
    )
    op.create_index("idx_teams_key", "teams", ["workspace_id", sa.text("upper(key)")], unique=True)

    op.create_table(
        "team_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        *_timestamps(updated=False),
        sa.CheckConstraint("role IN ('lead', 'member')", name=op.f("ck_team_members_role")),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_team_members_team_id_teams"),
            ondelete="CASCADE",
        ),
        _membership_fk("team_members"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_members")),
    )
    op.create_index("idx_team_members_unique", "team_members", ["team_id", "user_id"], unique=True)
    op.create_index("idx_team_members_lookup", "team_members", ["user_id", "workspace_id"])

    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="planned", nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("archived_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('planned', 'in_progress', 'paused', 'completed', 'canceled')",
            name=op.f("ck_projects_status"),
        ),
        sa.CheckConstraint(
            "start_date IS NULL OR target_date IS NULL OR target_date >= start_date",
            name=op.f("ck_projects_dates"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_projects_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_projects_team_id_teams"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["users.id"], name=op.f("fk_projects_lead_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(
        "idx_projects_team",
        "projects",
        ["workspace_id", "team_id"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "project_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        *_timestamps(updated=False),
        sa.CheckConstraint(
            "role IN ('admin', 'member', 'viewer')", name=op.f("ck_project_members_role")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_members_project_id_projects"),
            ondelete="CASCADE",
        ),
        _membership_fk("project_members"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_members")),
    )
    op.create_index(
        "idx_project_members_unique", "project_members", ["project_id", "user_id"], unique=True
    )
    op.create_index("idx_project_members_lookup", "project_members", ["user_id", "workspace_id"])

    op.create_table(
        "invitations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("invited_by", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("accepted_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("accepted_by", sa.UUID(), nullable=True),
        *_timestamps(updated=False),
        sa.CheckConstraint(
            "scope_type IN ('workspace', 'team', 'project')", name=op.f("ck_invitations_scope_type")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'expired', 'revoked')",
            name=op.f("ck_invitations_status"),
        ),
        sa.CheckConstraint(
            "(scope_type = 'workspace' AND role IN ('admin', 'member', 'guest'))"
            " OR (scope_type = 'team' AND role IN ('lead', 'member'))"
            " OR (scope_type = 'project' AND role IN ('admin', 'member', 'viewer'))",
            name=op.f("ck_invitations_role_matches_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_invitations_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name=op.f("fk_invitations_invited_by_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by"],
            ["users.id"],
            name=op.f("fk_invitations_accepted_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
    )
    op.create_index("idx_invitations_token", "invitations", ["token_hash"], unique=True)
    op.create_index(
        "idx_invitations_pending",
        "invitations",
        ["workspace_id", sa.text("lower(email)"), "scope_type", "scope_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    # Обратный порядок: сначала то, что ссылается, потом то, на что ссылаются.
    op.drop_table("invitations")
    op.drop_table("project_members")
    op.drop_table("projects")
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
