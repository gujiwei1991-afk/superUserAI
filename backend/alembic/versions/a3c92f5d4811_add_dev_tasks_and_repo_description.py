"""add dev_tasks table and repos.description

Revision ID: a3c92f5d4811
Revises: 6d981d2c5e92
Create Date: 2026-05-06 18:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'a3c92f5d4811'
down_revision: str | Sequence[str] | None = '6d981d2c5e92'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'repos',
        sa.Column('description', sa.Text(), nullable=True),
    )

    op.create_table(
        'dev_tasks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('repo_id', sa.Integer(), nullable=False),
        sa.Column('branch', sa.String(), nullable=True),
        sa.Column('pr_number', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['repo_id'], ['repos.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_dev_tasks_project_id', 'dev_tasks', ['project_id'])
    op.create_index('ix_dev_tasks_repo_id', 'dev_tasks', ['repo_id'])


def downgrade() -> None:
    op.drop_index('ix_dev_tasks_repo_id', table_name='dev_tasks')
    op.drop_index('ix_dev_tasks_project_id', table_name='dev_tasks')
    op.drop_table('dev_tasks')
    op.drop_column('repos', 'description')
