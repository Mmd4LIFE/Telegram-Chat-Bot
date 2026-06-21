"""initial star schema

Creates the dimension (users), content (messages), logs (model_selections,
migrations), fact (token_audits) and broadcast_logs tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- migration log (created first so it can record every revision) ---
    op.create_table(
        "migrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=False, server_default="upgrade"),
        sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_migrations_revision", "migrations", ["revision"])

    # --- users: DIMENSION (no measures) ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("is_bot", sa.Boolean(), server_default=sa.false()),
        sa.Column("is_premium", sa.Boolean(), server_default=sa.false()),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column("is_admin", sa.Boolean(), server_default=sa.false()),
        sa.Column("is_banned", sa.Boolean(), server_default=sa.false()),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_active", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    # --- messages: conversation content ---
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=16), server_default="text"),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_messages_user_id", "messages", ["user_id"])

    # --- model_selections: LOG of model choices (current = latest row) ---
    op.create_table(
        "model_selections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_model_selections_user_id", "model_selections", ["user_id"])
    op.create_index("ix_model_selections_created_at", "model_selections", ["created_at"])

    # --- token_audits: FACT (per-message token accounting, durable) ---
    op.create_table(
        "token_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content_type", sa.String(length=16), server_default="text"),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), server_default="0"),
        sa.Column("total_tokens", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_token_audits_user_id", "token_audits", ["user_id"])
    op.create_index("ix_token_audits_message_id", "token_audits", ["message_id"])
    op.create_index("ix_token_audits_created_at", "token_audits", ["created_at"])

    # --- broadcast_logs ---
    op.create_table(
        "broadcast_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sent_count", sa.Integer(), server_default="0"),
        sa.Column("failed_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("broadcast_logs")
    op.drop_index("ix_token_audits_created_at", table_name="token_audits")
    op.drop_index("ix_token_audits_message_id", table_name="token_audits")
    op.drop_index("ix_token_audits_user_id", table_name="token_audits")
    op.drop_table("token_audits")
    op.drop_index("ix_model_selections_created_at", table_name="model_selections")
    op.drop_index("ix_model_selections_user_id", table_name="model_selections")
    op.drop_table("model_selections")
    op.drop_index("ix_messages_user_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_migrations_revision", table_name="migrations")
    op.drop_table("migrations")
