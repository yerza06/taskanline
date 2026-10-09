"""Админ-панель: настройки инстанса, журнал аудита, сброс пароля, журнал входов.

Строка настроек создаётся здесь же, с `registration_mode = 'invite_only'`: открытая
регистрация на инстансе, доступном из интернета, должна включаться осознанно.

Revision ID: 0006_admin
Revises: 0005_views
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_admin"
down_revision: str | None = "0005_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTIFICATION_TYPES = "'mentioned', 'assigned', 'commented', 'state_changed'"


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_admin_audit_log_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_audit_log")),
    )
    op.create_index(
        "idx_audit_actor",
        "admin_audit_log",
        ["actor_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_audit_created", "admin_audit_log", [sa.literal_column("created_at DESC")], unique=False
    )
    op.create_index(
        "idx_audit_target",
        "admin_audit_log",
        ["target_type", "target_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_table(
        "instance_settings",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("instance_name", sa.Text(), server_default="TasKanLine", nullable=False),
        sa.Column(
            "registration_mode", sa.String(length=16), server_default="invite_only", nullable=False
        ),
        sa.Column(
            "allowed_email_domains",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("invitation_ttl_days", sa.SmallInteger(), server_default="7", nullable=False),
        sa.Column(
            "maintenance_mode", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "registration_mode IN ('invite_only', 'open', 'domain_allowlist')",
            name=op.f("ck_instance_settings_registration_mode"),
        ),
        sa.CheckConstraint("id = 1", name=op.f("ck_instance_settings_singleton")),
        sa.CheckConstraint(
            "invitation_ttl_days BETWEEN 1 AND 365",
            name=op.f("ck_instance_settings_invitation_ttl"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_instance_settings_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instance_settings")),
    )
    op.create_table(
        "login_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('password', 'registration', 'invitation', 'password_reset')",
            name=op.f("ck_login_events_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_login_events_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_events")),
    )
    op.create_index(
        "idx_login_events_user",
        "login_events",
        ["user_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=True),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_password_reset_tokens_requested_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_password_reset_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
    )
    op.create_index("idx_reset_token", "password_reset_tokens", ["token_hash"], unique=True)
    op.create_index(
        "idx_reset_user",
        "password_reset_tokens",
        ["user_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.add_column(
        "users", sa.Column("deleted_at", postgresql.TIMESTAMP(timezone=True), nullable=True)
    )

    op.execute("INSERT INTO instance_settings (id) VALUES (1)")
    op.drop_constraint(op.f("ck_notifications_type"), "notifications", type_="check")
    op.create_check_constraint(
        op.f("ck_notifications_type"),
        "notifications",
        f"type IN ({NOTIFICATION_TYPES}, 'ownership_granted')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type = 'ownership_granted'")
    op.drop_constraint(op.f("ck_notifications_type"), "notifications", type_="check")
    op.create_check_constraint(
        op.f("ck_notifications_type"), "notifications", f"type IN ({NOTIFICATION_TYPES})"
    )
    op.drop_column("users", "deleted_at")
    op.drop_index("idx_reset_user", table_name="password_reset_tokens")
    op.drop_index("idx_reset_token", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_index("idx_login_events_user", table_name="login_events")
    op.drop_table("login_events")
    op.drop_table("instance_settings")
    op.drop_index("idx_audit_target", table_name="admin_audit_log")
    op.drop_index("idx_audit_created", table_name="admin_audit_log")
    op.drop_index("idx_audit_actor", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
