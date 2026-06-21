"""System/operational tables: broadcast history and migration log."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BroadcastLog(Base):
    __tablename__ = "broadcast_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Migration(Base):
    """Log of every Alembic migration applied (written by the migration scripts)."""

    __tablename__ = "migrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    direction: Mapped[str] = mapped_column(String(16), default="upgrade")  # upgrade|downgrade
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
