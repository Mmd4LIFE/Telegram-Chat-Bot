"""store raw telegram identity on group_messages (don't depend on users table)

Group members who never started the bot must still be fully logged. We record
the sender's telegram_user_id (+ username/first_name snapshot) on every group
message; the internal users.id link is optional and filled in later if/when the
person starts the bot.

Revision ID: 0005_group_tg_id
Revises: 0004_groups_emoji
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_group_tg_id"
down_revision: Union[str, None] = "0004_groups_emoji"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("group_messages", sa.Column("telegram_user_id", sa.BigInteger(), nullable=True))
    op.add_column("group_messages", sa.Column("username", sa.String(length=255), nullable=True))
    op.add_column("group_messages", sa.Column("first_name", sa.String(length=255), nullable=True))

    # Backfill telegram identity for already-logged messages from the users table.
    op.execute(
        """
        UPDATE group_messages gm
        SET telegram_user_id = u.telegram_id,
            username = u.username,
            first_name = u.first_name
        FROM users u
        WHERE gm.user_id = u.id AND gm.telegram_user_id IS NULL
        """
    )
    op.create_index(
        "ix_group_messages_telegram_user_id", "group_messages", ["telegram_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_group_messages_telegram_user_id", table_name="group_messages")
    op.drop_column("group_messages", "first_name")
    op.drop_column("group_messages", "username")
    op.drop_column("group_messages", "telegram_user_id")
