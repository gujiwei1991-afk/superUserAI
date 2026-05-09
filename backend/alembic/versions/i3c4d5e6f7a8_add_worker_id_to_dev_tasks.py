"""add worker_id and partial unique index to dev_tasks

Revision ID: i3c4d5e6f7a8
Revises: h2b3c4d5e6f7
Create Date: 2026-05-09 20:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'i3c4d5e6f7a8'
down_revision: str | Sequence[str] | None = 'h2b3c4d5e6f7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ACTIVE_STATUSES = ('claimed', 'in_progress', 'pr_open', 'merged', 'deployed')


def upgrade() -> None:
    op.add_column(
        'dev_tasks',
        sa.Column('worker_id', sa.String(), nullable=True),
    )
    statuses_sql = ", ".join(f"'{s}'" for s in _ACTIVE_STATUSES)
    op.execute(
        f"CREATE UNIQUE INDEX idx_dev_tasks_active_per_project "
        f"ON dev_tasks (project_id) "
        f"WHERE status IN ({statuses_sql})"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_dev_tasks_active_per_project")
    op.drop_column('dev_tasks', 'worker_id')
