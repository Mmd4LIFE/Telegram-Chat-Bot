"""Group logging — groups the bot is in and every message sent in them.

When the bot is a member of a group (with privacy mode disabled in BotFather),
we log every message of every type. The captured content feeds per-user
personalization (favourite emojis, transcribed voice, topics, etc.).
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # group|supergroup
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)  # False once the bot is removed

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["GroupMessage"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class GroupMessage(Base):
    """Every message captured in a group, any media type."""

    __tablename__ = "group_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # text | photo | voice | audio | video | video_note | sticker | animation |
    # document | poll | location | contact | other
    message_type: Mapped[str] = mapped_column(String(24), default="text", index=True)

    text: Mapped[str | None] = mapped_column(Text, nullable=True)          # text or caption
    transcription: Mapped[str | None] = mapped_column(Text, nullable=True)  # voice/video_note → text
    emojis: Mapped[str | None] = mapped_column(String(255), nullable=True)  # extracted emojis, joined
    sticker_emoji: Mapped[str | None] = mapped_column(String(16), nullable=True)
    file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)  # sticker/media file id
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)     # seconds, for audio/video

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    group: Mapped["Group"] = relationship(back_populates="messages")
