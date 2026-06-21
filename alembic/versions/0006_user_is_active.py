"""add users.is_active (non-active = discovered via group, not yet started bot)

Additive & production-safe. Existing users default to active.

Revision ID: 0006_user_active
Revises: 0005_group_tg_id
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_user_active"
down_revision: Union[str, None] = "0005_group_tg_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_users_is_active", "users", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_column("users", "is_active")
