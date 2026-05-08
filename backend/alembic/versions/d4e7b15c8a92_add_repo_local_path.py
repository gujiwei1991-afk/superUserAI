"""add repos.local_path

Revision ID: d4e7b15c8a92
Revises: c8f3a91b2e47
Create Date: 2026-05-08 09:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e7b15c8a92'
down_revision: str | Sequence[str] | None = 'c8f3a91b2e47'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'repos',
        sa.Column('local_path', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('repos', 'local_path')
