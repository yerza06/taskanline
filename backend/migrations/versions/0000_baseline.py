"""Базовая ревизия: точка отсчёта без таблиц.

Реальные таблицы начинаются с 0001_users_auth на этапе 1. Пустая ревизия нужна,
чтобы у миграций была голова уже на этапе 0 — и `upgrade head` работал на чистой базе.

Revision ID: 0000_baseline
Revises:
Create Date: 2026-09-18
"""

from collections.abc import Sequence

revision: str = "0000_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
