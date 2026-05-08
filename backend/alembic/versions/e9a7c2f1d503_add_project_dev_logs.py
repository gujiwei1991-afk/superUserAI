"""add project_dev_logs

Revision ID: e9a7c2f1d503
Revises: d4e7b15c8a92
Create Date: 2026-05-08 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e9a7c2f1d503'
down_revision: str | Sequence[str] | None = 'd4e7b15c8a92'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'project_dev_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['project_id'],
            ['projects.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_project_dev_logs_project_created',
        'project_dev_logs',
        ['project_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_project_dev_logs_project_created', table_name='project_dev_logs')
    op.drop_table('project_dev_logs')
