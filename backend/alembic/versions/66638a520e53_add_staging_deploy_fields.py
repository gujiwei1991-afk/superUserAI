"""add staging deploy fields

Revision ID: 66638a520e53
Revises: i3c4d5e6f7a8
Create Date: 2026-05-10 14:11:27.024747

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "66638a520e53"
down_revision: str | Sequence[str] | None = "i3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("repos", sa.Column("staging_url", sa.Text(), nullable=True))
    op.add_column("repos", sa.Column("staging_ssh_target", sa.String(length=255), nullable=True))
    op.add_column("repos", sa.Column("staging_deploy_path", sa.Text(), nullable=True))
    op.add_column(
        "repos",
        sa.Column(
            "staging_compose_file",
            sa.String(length=255),
            nullable=False,
            server_default="docker-compose.staging.yml",
        ),
    )
    op.add_column(
        "dev_tasks",
        sa.Column(
            "staging_deploy_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column("dev_tasks", sa.Column("staging_deployed_at", sa.DateTime(), nullable=True))
    op.add_column("dev_tasks", sa.Column("staging_deploy_log", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("dev_tasks", "staging_deploy_log")
    op.drop_column("dev_tasks", "staging_deployed_at")
    op.drop_column("dev_tasks", "staging_deploy_status")
    op.drop_column("repos", "staging_compose_file")
    op.drop_column("repos", "staging_deploy_path")
    op.drop_column("repos", "staging_ssh_target")
    op.drop_column("repos", "staging_url")
