"""add users.is_active and seed admin/granted users

Revision ID: c8f3a91b2e47
Revises: a3c92f5d4811
Create Date: 2026-05-07 09:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c8f3a91b2e47'
down_revision: str | Sequence[str] | None = 'a3c92f5d4811'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )

    op.execute("UPDATE users SET is_active = TRUE WHERE role = 'admin'")
    op.execute(
        "UPDATE users SET is_active = TRUE "
        "WHERE id IN (SELECT DISTINCT user_id FROM user_repos)"
    )


def downgrade() -> None:
    op.drop_column('users', 'is_active')
