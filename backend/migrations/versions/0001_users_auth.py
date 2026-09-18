"""Таблицы аутентификации: users, refresh_tokens, api_tokens.

Первая ревизия с реальными таблицами. Расширение citext создаётся здесь же:
email хранится регистронезависимо, и без расширения тип колонки не существует.

Revision ID: 0001_users_auth
Revises: 0000_baseline
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_users_auth"
down_revision: str | None = "0000_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("role", sa.String(length=16), server_default="user", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_seen_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role IN ('superadmin', 'admin', 'support', 'user')", name=op.f("ck_users_role")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=True)
    # Частичный: администраторов единицы, а строк в таблице — все.
    op.create_index(
        "idx_users_admins",
        "users",
        ["role"],
        unique=False,
        postgresql_where=sa.text("role <> 'user'"),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
    )
    op.create_index("idx_refresh_tokens_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("idx_refresh_tokens_user", "refresh_tokens", ["user_id"], unique=False)

    op.create_table(
        "api_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=12), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_used_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("scope IN ('read', 'read_write')", name=op.f("ck_api_tokens_scope")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_api_tokens_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_tokens")),
    )
    op.create_index("idx_api_tokens_hash", "api_tokens", ["token_hash"], unique=True)
    op.create_index("idx_api_tokens_user", "api_tokens", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_api_tokens_user", table_name="api_tokens")
    op.drop_index("idx_api_tokens_hash", table_name="api_tokens")
    op.drop_table("api_tokens")

    op.drop_index("idx_refresh_tokens_user", table_name="refresh_tokens")
    op.drop_index("idx_refresh_tokens_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index(
        "idx_users_admins", table_name="users", postgresql_where=sa.text("role <> 'user'")
    )
    op.drop_index("idx_users_email", table_name="users")
    op.drop_table("users")

    # Расширение снимается последним: до этого от него зависит колонка email.
    op.execute("DROP EXTENSION IF EXISTS citext")
