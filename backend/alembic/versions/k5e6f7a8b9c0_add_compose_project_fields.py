"""add compose project (docker compose -p) fields

Revision ID: k5e6f7a8b9c0
Revises: j4d5e6f7a8b9
Create Date: 2026-05-30 10:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "k5e6f7a8b9c0"
down_revision: str | Sequence[str] | None = "j4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "repos",
        sa.Column("staging_compose_project", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "repos",
        sa.Column("prod_compose_project", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("repos", "prod_compose_project")
    op.drop_column("repos", "staging_compose_project")
