"""add users.segment and users.segment_notified

Auto-segmentation: the user's current primary tag and the last tag value we
notified them about. Additive & production-safe (nullable columns).

Revision ID: 0003_user_segment
Revises: 0002_conv_tags_mem
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_user_segment"
down_revision: Union[str, None] = "0002_conv_tags_mem"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("segment", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("segment_notified", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "segment_notified")
    op.drop_column("users", "segment")
