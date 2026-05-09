"""add media_url + media_type to messages

Revision ID: h2b3c4d5e6f7
Revises: g1a2b3c4d5e6
Create Date: 2026-05-09 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'h2b3c4d5e6f7'
down_revision: str | Sequence[str] | None = 'g1a2b3c4d5e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('media_url', sa.Text(), nullable=True),
    )
    op.add_column(
        'messages',
        sa.Column('media_type', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('messages', 'media_type')
    op.drop_column('messages', 'media_url')
