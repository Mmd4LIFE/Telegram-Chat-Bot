"""Database models.

Schema is organised as a small star schema:

  • users            — DIMENSION: descriptive attributes of a user only
                       (no measures / running totals live here).
  • messages         — conversation content store (prunable on "new chat").
  • model_selections — LOG: one row every time a user picks a model. The user's
                       *current* model is simply the most recent row.
  • token_audits     — FACT: per-message token accounting (durable; survives a
                       conversation reset so usage history is never lost).
  • broadcast_logs   — admin broadcast history.
  • migrations       — LOG of every Alembic migration applied (written by the
                       migrations themselves; complements `alembic_version`).
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """Dimension table — who the user is. No measures stored here."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # App-level state (attributes, not measures)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    model_selections: Mapped[list["ModelSelection"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    token_audits: Mapped[list["TokenAudit"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p) or (
            self.username or str(self.telegram_id)
        )


class Message(Base):
    """Conversation content (may be cleared when a user starts a new chat)."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    role: Mapped[str] = mapped_column(String(16))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(16), default="text")  # text|image|voice
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="messages")


class ModelSelection(Base):
    """Log of model choices. Current model for a user = latest row."""

    __tablename__ = "model_selections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user: Mapped["User"] = relationship(back_populates="model_selections")


class TokenAudit(Base):
    """Fact table — token accounting for every AI interaction.

    Durable: `message_id` is SET NULL if the underlying message is later pruned,
    so usage/billing history is preserved across conversation resets.
    """

    __tablename__ = "token_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )

    role: Mapped[str] = mapped_column(String(16))
    content_type: Mapped[str] = mapped_column(String(16), default="text")
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user: Mapped["User"] = relationship(back_populates="token_audits")


class BroadcastLog(Base):
    __tablename__ = "broadcast_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Migration(Base):
    """Log of every Alembic migration that has been applied (written by the
    migration scripts). `alembic_version` only keeps the *current* head; this
    keeps the full history with timestamps and direction."""

    __tablename__ = "migrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    direction: Mapped[str] = mapped_column(String(16), default="upgrade")  # upgrade|downgrade
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
