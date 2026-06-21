"""User dimension and user-attached side tables (tags, memories, emoji stats)."""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
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

    # Auto segmentation: `segment` is the user's current primary tag, recomputed
    # at the end of each conversation; `segment_notified` is the last tag value
    # we told the user about (so we only message them when it changes).
    segment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    segment_notified: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    model_selections: Mapped[list["ModelSelection"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    token_audits: Mapped[list["TokenAudit"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    tags: Mapped[list["UserTag"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p) or (
            self.username or str(self.telegram_id)
        )


class UserTag(Base):
    """Segmentation badge attached to a user (e.g. tech_user, power_user)."""

    __tablename__ = "user_tags"
    __table_args__ = (UniqueConstraint("user_id", "tag", name="uq_user_tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tag: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16), default="admin")  # admin|auto
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="tags")


class UserMemory(Base):
    """Relational mirror of personalization facts stored in the vector engine."""

    __tablename__ = "user_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    vector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(String(24), default="message")  # message|fact|preference|group
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserEmojiStat(Base):
    """Per-user emoji usage counts (for emoji-aware personalization)."""

    __tablename__ = "user_emoji_stats"
    __table_args__ = (UniqueConstraint("user_id", "emoji", name="uq_user_emoji"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    emoji: Mapped[str] = mapped_column(String(16))
    count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
