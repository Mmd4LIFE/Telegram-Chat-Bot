"""Database helpers for group logging and emoji statistics."""
from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Group, GroupMessage, UserEmojiStat


async def register_group(session: AsyncSession, chat) -> Group:
    """Insert/refresh a group row when the bot sees activity there."""
    result = await session.execute(select(Group).where(Group.chat_id == chat.id))
    group = result.scalar_one_or_none()
    if group is None:
        group = Group(
            chat_id=chat.id,
            title=getattr(chat, "title", None),
            type=getattr(chat, "type", None),
            username=getattr(chat, "username", None),
            is_active=True,
        )
        session.add(group)
        await session.commit()
        await session.refresh(group)
        return group
    group.title = getattr(chat, "title", None) or group.title
    group.type = getattr(chat, "type", None) or group.type
    group.username = getattr(chat, "username", None)
    group.is_active = True
    await session.commit()
    return group


async def set_group_active(session: AsyncSession, chat_id: int, active: bool) -> None:
    result = await session.execute(select(Group).where(Group.chat_id == chat_id))
    group = result.scalar_one_or_none()
    if group:
        group.is_active = active
        await session.commit()


async def save_group_message(
    session: AsyncSession,
    group_id: int,
    *,
    user_id: int | None,
    telegram_message_id: int | None,
    message_type: str,
    text: str | None = None,
    transcription: str | None = None,
    emojis: str | None = None,
    sticker_emoji: str | None = None,
    file_id: str | None = None,
    duration: int | None = None,
) -> GroupMessage:
    gm = GroupMessage(
        group_id=group_id,
        user_id=user_id,
        telegram_message_id=telegram_message_id,
        message_type=message_type,
        text=text,
        transcription=transcription,
        emojis=emojis,
        sticker_emoji=sticker_emoji,
        file_id=file_id,
        duration=duration,
    )
    session.add(gm)
    grp = await session.get(Group, group_id)
    if grp:
        grp.last_message_at = func.now()
    await session.commit()
    return gm


async def increment_emojis(session: AsyncSession, user_id: int, emojis: list[str]) -> None:
    """Upsert per-user emoji counts (Postgres ON CONFLICT)."""
    if not emojis:
        return
    counts: dict[str, int] = {}
    for e in emojis:
        counts[e] = counts.get(e, 0) + 1
    for emoji, n in counts.items():
        stmt = (
            pg_insert(UserEmojiStat)
            .values(user_id=user_id, emoji=emoji, count=n)
            .on_conflict_do_update(
                constraint="uq_user_emoji",
                set_={"count": UserEmojiStat.count + n, "updated_at": func.now()},
            )
        )
        await session.execute(stmt)
    await session.commit()


async def top_emojis(session: AsyncSession, user_id: int, limit: int = 5) -> list[tuple[str, int]]:
    result = await session.execute(
        select(UserEmojiStat.emoji, UserEmojiStat.count)
        .where(UserEmojiStat.user_id == user_id)
        .order_by(desc(UserEmojiStat.count))
        .limit(limit)
    )
    return [(e, c) for e, c in result.all()]


async def favorite_sticker_file_id(session: AsyncSession, user_id: int) -> str | None:
    """Most-recent sticker file_id the user sent in a group (for echoing back)."""
    result = await session.execute(
        select(GroupMessage.file_id)
        .where(GroupMessage.user_id == user_id, GroupMessage.message_type == "sticker")
        .order_by(desc(GroupMessage.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def group_stats(session: AsyncSession) -> dict:
    total_groups = await session.scalar(select(func.count(Group.id)))
    active_groups = await session.scalar(
        select(func.count(Group.id)).where(Group.is_active == True)  # noqa: E712
    )
    total_group_messages = await session.scalar(select(func.count(GroupMessage.id)))
    return {
        "total_groups": total_groups or 0,
        "active_groups": active_groups or 0,
        "total_group_messages": total_group_messages or 0,
    }
