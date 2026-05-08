"""add projects.wechat_group_id

Revision ID: f3a8c4b2e019
Revises: e9a7c2f1d503
Create Date: 2026-05-08 17:45:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'f3a8c4b2e019'
down_revision: str | Sequence[str] | None = 'e9a7c2f1d503'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column('wechat_group_id', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('projects', 'wechat_group_id')
