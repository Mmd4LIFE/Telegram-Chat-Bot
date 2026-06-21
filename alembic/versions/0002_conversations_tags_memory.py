"""conversations, message.conversation_id, user_tags, user_memories

Additive & production-safe: creates new tables and columns, then backfills
existing messages into a per-user "Imported chat" conversation so the new
NOT NULL constraint on messages.conversation_id holds. No data is dropped.

Revision ID: 0002_conv_tags_mem
Revises: 0001_initial
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_conv_tags_mem"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- conversations ---
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_index("ix_conversations_is_active", "conversations", ["is_active"])

    # --- messages.conversation_id (nullable first, backfill, then NOT NULL) ---
    op.add_column("messages", sa.Column("conversation_id", sa.Integer(), nullable=True))
    op.add_column("token_audits", sa.Column("conversation_id", sa.Integer(), nullable=True))

    # Backfill: one "Imported chat" conversation per user that has messages.
    op.execute(
        """
        INSERT INTO conversations (user_id, title, is_active, created_at, updated_at)
        SELECT DISTINCT user_id, 'Imported chat', false, now(), now()
        FROM messages
        WHERE conversation_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE messages m
        SET conversation_id = c.id
        FROM conversations c
        WHERE c.user_id = m.user_id AND m.conversation_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE token_audits ta
        SET conversation_id = m.conversation_id
        FROM messages m
        WHERE ta.message_id = m.id AND ta.conversation_id IS NULL
        """
    )

    op.alter_column("messages", "conversation_id", nullable=False)
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_token_audits_conversation_id", "token_audits", ["conversation_id"])
    op.create_foreign_key(
        "fk_messages_conversation", "messages", "conversations",
        ["conversation_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_token_audits_conversation", "token_audits", "conversations",
        ["conversation_id"], ["id"], ondelete="SET NULL",
    )

    # --- user_tags ---
    op.create_table(
        "user_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=16), server_default="admin"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "tag", name="uq_user_tag"),
    )
    op.create_index("ix_user_tags_user_id", "user_tags", ["user_id"])

    # --- user_memories (relational mirror of vectors in Qdrant) ---
    op.create_table(
        "user_memories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("vector_id", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=24), server_default="message"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_user_memories_user_id", "user_memories", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_memories_user_id", table_name="user_memories")
    op.drop_table("user_memories")
    op.drop_index("ix_user_tags_user_id", table_name="user_tags")
    op.drop_table("user_tags")

    op.drop_constraint("fk_token_audits_conversation", "token_audits", type_="foreignkey")
    op.drop_constraint("fk_messages_conversation", "messages", type_="foreignkey")
    op.drop_index("ix_token_audits_conversation_id", table_name="token_audits")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_column("token_audits", "conversation_id")
    op.drop_column("messages", "conversation_id")

    op.drop_index("ix_conversations_is_active", table_name="conversations")
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_table("conversations")
