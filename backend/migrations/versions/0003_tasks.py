"""Ядро задач: workflow_states, tasks, task_relations, labels, task_labels, idempotency_keys.

Командам, созданным до этой ревизии, досоздаётся стандартный набор статусов: без
статуса по умолчанию в команде нельзя завести ни одной задачи. Набор продублирован
здесь, а не импортирован из приложения: ревизия не должна меняться вместе с кодом.

Revision ID: 0003_tasks
Revises: 0002_org
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from uuid6 import uuid7

revision: str = "0003_tasks"
down_revision: str | None = "0002_org"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (name, type, color, is_default) — порядок списка и есть position.
DEFAULT_STATES = [
    ("Backlog", "backlog", "#bec2c8", False),
    ("Todo", "unstarted", "#e2e2e2", True),
    ("In Progress", "started", "#f2c94c", False),
    ("Done", "completed", "#5e6ad2", False),
    ("Canceled", "canceled", "#95a2b3", False),
]


def _created_at() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "created_at",
        postgresql.TIMESTAMP(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _workspace_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["workspaces.id"],
        name=f"fk_{table}_workspace_id_workspaces",
        ondelete="CASCADE",
    )


def upgrade() -> None:
    states = op.create_table(
        "workflow_states",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "type IN ('backlog', 'unstarted', 'started', 'completed', 'canceled')",
            name=op.f("ck_workflow_states_type"),
        ),
        sa.CheckConstraint(
            "color ~ '^#[0-9a-fA-F]{6}$'", name=op.f("ck_workflow_states_color_format")
        ),
        _workspace_fk("workflow_states"),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_workflow_states_team_id_teams"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_states")),
    )
    op.create_index(
        "idx_states_name", "workflow_states", ["team_id", sa.text("lower(name)")], unique=True
    )
    op.create_index(
        "idx_states_default",
        "workflow_states",
        ["team_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("state_id", sa.UUID(), nullable=False),
        sa.Column("assignee_id", sa.UUID(), nullable=True),
        sa.Column("creator_id", sa.UUID(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        # Побайтовое сравнение: алфавит дробного индекса упорядочен по ASCII.
        sa.Column("sort_order", sa.Text(collation="C"), nullable=False),
        sa.Column("estimate", sa.SmallInteger(), nullable=True),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        _created_at(),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("priority BETWEEN 0 AND 4", name=op.f("ck_tasks_priority")),
        sa.CheckConstraint(
            "char_length(title) BETWEEN 1 AND 500", name=op.f("ck_tasks_title_length")
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name=op.f("ck_tasks_no_self_parent")
        ),
        _workspace_fk("tasks"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_tasks_team_id_teams"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_tasks_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["state_id"],
            ["workflow_states.id"],
            name=op.f("fk_tasks_state_id_workflow_states"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["users.id"],
            name=op.f("fk_tasks_assignee_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["creator_id"],
            ["users.id"],
            name=op.f("fk_tasks_creator_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["tasks.id"], name=op.f("fk_tasks_parent_id_tasks"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index("idx_tasks_key", "tasks", ["team_id", "number"], unique=True)
    op.create_index(
        "idx_tasks_board",
        "tasks",
        ["workspace_id", "team_id", "state_id", "sort_order"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_tasks_assignee",
        "tasks",
        ["workspace_id", "assignee_id", "state_id"],
        postgresql_where=sa.text("deleted_at IS NULL AND assignee_id IS NOT NULL"),
    )
    op.create_index(
        "idx_tasks_project",
        "tasks",
        ["workspace_id", "project_id", "sort_order"],
        postgresql_where=sa.text("deleted_at IS NULL AND project_id IS NOT NULL"),
    )
    op.create_index(
        "idx_tasks_parent", "tasks", ["parent_id"], postgresql_where=sa.text("parent_id IS NOT NULL")
    )
    op.create_index(
        "idx_tasks_due",
        "tasks",
        ["workspace_id", "due_date"],
        postgresql_where=sa.text("deleted_at IS NULL AND due_date IS NOT NULL"),
    )
    op.create_index(
        "idx_tasks_search",
        "tasks",
        [sa.text("to_tsvector('simple', title || ' ' || coalesce(description, ''))")],
        postgresql_using="gin",
    )

    op.create_table(
        "task_relations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("source_task_id", sa.UUID(), nullable=False),
        sa.Column("target_task_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "type IN ('blocks', 'relates_to', 'duplicates')", name=op.f("ck_task_relations_type")
        ),
        sa.CheckConstraint(
            "source_task_id <> target_task_id", name=op.f("ck_task_relations_no_self")
        ),
        _workspace_fk("task_relations"),
        sa.ForeignKeyConstraint(
            ["source_task_id"],
            ["tasks.id"],
            name=op.f("fk_task_relations_source_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_task_id"],
            ["tasks.id"],
            name=op.f("fk_task_relations_target_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_task_relations_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_relations")),
    )
    op.create_index(
        "idx_relations_unique",
        "task_relations",
        ["source_task_id", "target_task_id", "type"],
        unique=True,
    )
    op.create_index("idx_relations_target", "task_relations", ["target_task_id"])

    op.create_table(
        "labels",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        _created_at(),
        sa.CheckConstraint("color ~ '^#[0-9a-fA-F]{6}$'", name=op.f("ck_labels_color_format")),
        _workspace_fk("labels"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_labels_team_id_teams"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_labels")),
    )
    op.create_index(
        "idx_labels_ws",
        "labels",
        ["workspace_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("team_id IS NULL"),
    )
    op.create_index(
        "idx_labels_team",
        "labels",
        ["team_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("team_id IS NOT NULL"),
    )

    op.create_table(
        "task_labels",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("label_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_task_labels_task_id_tasks"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["label_id"],
            ["labels.id"],
            name=op.f("fk_task_labels_label_id_labels"),
            ondelete="CASCADE",
        ),
        _workspace_fk("task_labels"),
        sa.PrimaryKeyConstraint("task_id", "label_id", name=op.f("pk_task_labels")),
    )
    op.create_index("idx_task_labels_label", "task_labels", ["label_id", "task_id"])

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("response_status", sa.SmallInteger(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_idempotency_keys_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("key", "user_id", name=op.f("pk_idempotency_keys")),
    )
    op.create_index("idx_idempotency_gc", "idempotency_keys", ["created_at"])

    teams = op.get_bind().execute(sa.text("SELECT id, workspace_id FROM teams")).all()
    rows = [
        {
            "id": uuid7(),
            "workspace_id": workspace_id,
            "team_id": team_id,
            "name": name,
            "type": kind,
            "color": color,
            "position": position,
            "is_default": is_default,
        }
        for team_id, workspace_id in teams
        for position, (name, kind, color, is_default) in enumerate(DEFAULT_STATES)
    ]
    if rows:
        op.bulk_insert(states, rows)


def downgrade() -> None:
    # Обратный порядок: сначала то, что ссылается, потом то, на что ссылаются.
    op.drop_table("idempotency_keys")
    op.drop_table("task_labels")
    op.drop_table("labels")
    op.drop_table("task_relations")
    op.drop_table("tasks")
    op.drop_table("workflow_states")
