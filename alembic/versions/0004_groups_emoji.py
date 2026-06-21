"""group logging tables + per-user emoji stats

Additive & production-safe.

Revision ID: 0004_groups_emoji
Revises: 0003_user_segment
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_groups_emoji"
down_revision: Union[str, None] = "0003_user_segment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_groups_chat_id", "groups", ["chat_id"], unique=True)

    op.create_table(
        "group_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("message_type", sa.String(length=24), server_default="text"),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("transcription", sa.Text(), nullable=True),
        sa.Column("emojis", sa.String(length=255), nullable=True),
        sa.Column("sticker_emoji", sa.String(length=16), nullable=True),
        sa.Column("file_id", sa.String(length=256), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_group_messages_group_id", "group_messages", ["group_id"])
    op.create_index("ix_group_messages_user_id", "group_messages", ["user_id"])
    op.create_index("ix_group_messages_message_type", "group_messages", ["message_type"])
    op.create_index("ix_group_messages_created_at", "group_messages", ["created_at"])

    op.create_table(
        "user_emoji_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("emoji", sa.String(length=16), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "emoji", name="uq_user_emoji"),
    )
    op.create_index("ix_user_emoji_stats_user_id", "user_emoji_stats", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_emoji_stats_user_id", table_name="user_emoji_stats")
    op.drop_table("user_emoji_stats")
    op.drop_index("ix_group_messages_created_at", table_name="group_messages")
    op.drop_index("ix_group_messages_message_type", table_name="group_messages")
    op.drop_index("ix_group_messages_user_id", table_name="group_messages")
    op.drop_index("ix_group_messages_group_id", table_name="group_messages")
    op.drop_table("group_messages")
    op.drop_index("ix_groups_chat_id", table_name="groups")
    op.drop_table("groups")
