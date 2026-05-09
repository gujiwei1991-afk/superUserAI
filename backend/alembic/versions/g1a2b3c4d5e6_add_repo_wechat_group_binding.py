"""add wechat_group binding to repos

Revision ID: g1a2b3c4d5e6
Revises: f3a8c4b2e019
Create Date: 2026-05-09 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'g1a2b3c4d5e6'
down_revision: str | Sequence[str] | None = 'f3a8c4b2e019'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'repos',
        sa.Column('wechat_group_id', sa.String(), nullable=True),
    )
    op.add_column(
        'repos',
        sa.Column('wechat_group_bound_at', sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column(
        'repos',
        sa.Column(
            'wechat_group_bound_by',
            sa.Integer(),
            sa.ForeignKey('users.id'),
            nullable=True,
        ),
    )
    op.create_index(
        'ix_repos_wechat_group_id',
        'repos',
        ['wechat_group_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_repos_wechat_group_id', table_name='repos')
    op.drop_column('repos', 'wechat_group_bound_by')
    op.drop_column('repos', 'wechat_group_bound_at')
    op.drop_column('repos', 'wechat_group_id')
