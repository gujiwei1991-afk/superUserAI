"""add production deploy fields

Revision ID: j4d5e6f7a8b9
Revises: 66638a520e53
Create Date: 2026-05-23 10:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "j4d5e6f7a8b9"
down_revision: str | Sequence[str] | None = "66638a520e53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("repos", sa.Column("prod_url", sa.Text(), nullable=True))
    op.add_column("repos", sa.Column("prod_ssh_target", sa.String(length=255), nullable=True))
    op.add_column("repos", sa.Column("prod_deploy_path", sa.Text(), nullable=True))
    op.add_column(
        "repos",
        sa.Column(
            "prod_compose_file",
            sa.String(length=255),
            nullable=False,
            server_default="docker-compose.prod.yml",
        ),
    )
    op.add_column(
        "repos",
        sa.Column(
            "prod_run_migrations",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "dev_tasks",
        sa.Column(
            "prod_deploy_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column("dev_tasks", sa.Column("prod_deployed_at", sa.DateTime(), nullable=True))
    op.add_column("dev_tasks", sa.Column("prod_deploy_log", sa.Text(), nullable=True))
    op.add_column("dev_tasks", sa.Column("prod_deployed_sha", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("dev_tasks", "prod_deployed_sha")
    op.drop_column("dev_tasks", "prod_deploy_log")
    op.drop_column("dev_tasks", "prod_deployed_at")
    op.drop_column("dev_tasks", "prod_deploy_status")
    op.drop_column("repos", "prod_run_migrations")
    op.drop_column("repos", "prod_compose_file")
    op.drop_column("repos", "prod_deploy_path")
    op.drop_column("repos", "prod_ssh_target")
    op.drop_column("repos", "prod_url")
