"""web_searches log table (@web queries, answers, source links)

Additive & production-safe.

Revision ID: 0007_web_searches
Revises: 0006_user_active
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0007_web_searches"
down_revision: Union[str, None] = "0006_user_active"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "web_searches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("sources", JSONB(), nullable=True),
        sa.Column("result_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_web_searches_user_id", "web_searches", ["user_id"])
    op.create_index("ix_web_searches_created_at", "web_searches", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_web_searches_created_at", table_name="web_searches")
    op.drop_index("ix_web_searches_user_id", table_name="web_searches")
    op.drop_table("web_searches")
