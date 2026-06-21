"""Database access helpers (star-schema aware)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    BroadcastLog,
    Conversation,
    Message,
    ModelSelection,
    TokenAudit,
    User,
    UserMemory,
    UserTag,
    WebSearch,
)


async def get_or_create_user(session: AsyncSession, tg_user, *, active: bool = True) -> User:
    """Fetch a user by telegram id, creating/refreshing their profile.

    `active=False` is used when we discover a member purely via group logging:
    the user row is created but flagged non-active until they DM the bot. A later
    direct interaction (`active=True`) promotes them to active.
    """
    result = await session.execute(select(User).where(User.telegram_id == tg_user.id))
    user = result.scalar_one_or_none()

    is_admin = tg_user.id == settings.admin_telegram_id

    if user is None:
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            language_code=tg_user.language_code,
            is_bot=bool(tg_user.is_bot),
            is_premium=bool(getattr(tg_user, "is_premium", False)),
            is_active=active,
            is_admin=is_admin,
        )
        session.add(user)
        await session.flush()
        # seed the initial model selection so the user has a "current" model
        session.add(ModelSelection(user_id=user.id, model=settings.default_model))
        # seed the first (active) conversation
        session.add(Conversation(user_id=user.id, is_active=True))
        await session.commit()
        await session.refresh(user)
        return user

    user.username = tg_user.username
    user.first_name = tg_user.first_name
    user.last_name = tg_user.last_name
    user.language_code = tg_user.language_code
    user.is_premium = bool(getattr(tg_user, "is_premium", False))
    if active and not user.is_active:
        user.is_active = True  # promote: they've now used the bot directly
    if is_admin:
        user.is_admin = True
    await session.commit()
    return user


# ───────────────────────── Model selection (log) ─────────────────────────

async def get_current_model(session: AsyncSession, user: User) -> str:
    """Current model = most recent model_selections row for the user."""
    result = await session.execute(
        select(ModelSelection.model)
        .where(ModelSelection.user_id == user.id)
        .order_by(desc(ModelSelection.created_at), desc(ModelSelection.id))
        .limit(1)
    )
    model = result.scalar_one_or_none()
    return model or settings.default_model


async def set_model(session: AsyncSession, user: User, model: str) -> None:
    """Record a model choice (append-only log)."""
    session.add(ModelSelection(user_id=user.id, model=model))
    await session.commit()


async def set_phone(session: AsyncSession, user: User, phone: str) -> None:
    user.phone_number = phone
    await session.commit()


async def set_system_prompt(session: AsyncSession, user: User, prompt: str | None) -> None:
    user.system_prompt = prompt
    await session.commit()


# ───────────────────────────── Conversations ─────────────────────────────

async def get_active_conversation(session: AsyncSession, user: User) -> Conversation:
    """Return the user's active conversation, creating one if needed."""
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.is_active == True)  # noqa: E712
        .order_by(desc(Conversation.id))
        .limit(1)
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        conv = Conversation(user_id=user.id, is_active=True)
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
    return conv


async def start_new_conversation(session: AsyncSession, user: User) -> Conversation:
    """Archive the current conversation and open a fresh active one."""
    result = await session.execute(
        select(Conversation).where(
            Conversation.user_id == user.id, Conversation.is_active == True  # noqa: E712
        )
    )
    for conv in result.scalars().all():
        conv.is_active = False
    new_conv = Conversation(user_id=user.id, is_active=True)
    session.add(new_conv)
    await session.commit()
    await session.refresh(new_conv)
    return new_conv


async def set_active_conversation(session: AsyncSession, user: User, conv_id: int) -> Conversation | None:
    """Resume a previous conversation (make it the active one)."""
    target = await session.get(Conversation, conv_id)
    if not target or target.user_id != user.id:
        return None
    result = await session.execute(
        select(Conversation).where(
            Conversation.user_id == user.id, Conversation.is_active == True  # noqa: E712
        )
    )
    for conv in result.scalars().all():
        conv.is_active = False
    target.is_active = True
    await session.commit()
    return target


async def list_conversations(
    session: AsyncSession, user: User, limit: int = 10
) -> list[tuple[Conversation, int]]:
    """Recent conversations (that have messages) → (conversation, message_count)."""
    rows = await session.execute(
        select(Conversation, func.count(Message.id))
        .join(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == user.id)
        .group_by(Conversation.id)
        .order_by(desc(Conversation.updated_at))
        .limit(limit)
    )
    return [(c, int(n)) for c, n in rows.all()]


async def conversation_transcript(session: AsyncSession, conv_id: int, limit: int = 12) -> str:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at)
        .limit(limit)
    )
    return "\n".join(f"{m.role}: {m.content}" for m in result.scalars().all())


async def set_conversation_title(session: AsyncSession, conv_id: int, title: str) -> None:
    conv = await session.get(Conversation, conv_id)
    if conv:
        conv.title = title
        await session.commit()


async def stale_active_conversations(
    session: AsyncSession, hours: int, limit: int = 50
) -> list[tuple[Conversation, User]]:
    """Active conversations idle for `hours`, belonging to active (started) users,
    that contain at least one USER message (so there's context to follow up on and
    we never nag an unanswered bot-initiated chat)."""
    threshold = datetime.now(timezone.utc) - timedelta(hours=hours)
    has_user_msg = (
        select(Message.id)
        .where(Message.conversation_id == Conversation.id, Message.role == "user")
        .exists()
    )
    rows = await session.execute(
        select(Conversation, User)
        .join(User, User.id == Conversation.user_id)
        .where(
            Conversation.is_active == True,  # noqa: E712
            User.is_active == True,  # noqa: E712
            User.is_banned == False,  # noqa: E712
            func.coalesce(Conversation.last_message_at, Conversation.created_at) < threshold,
            has_user_msg,
        )
        .limit(limit)
    )
    return [(c, u) for c, u in rows.all()]


# ───────────────────────── Messages + token audit ─────────────────────────

async def save_message(
    session: AsyncSession,
    user: User,
    role: str,
    content: str,
    *,
    content_type: str = "text",
    model: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    telegram_message_id: int | None = None,
    conversation_id: int | None = None,
) -> Message:
    """Persist conversation content (messages) AND a durable token audit row."""
    if conversation_id is None:
        conversation_id = (await get_active_conversation(session, user)).id

    msg = Message(
        user_id=user.id,
        conversation_id=conversation_id,
        role=role,
        content=content,
        content_type=content_type,
        model=model,
        telegram_message_id=telegram_message_id,
    )
    session.add(msg)
    await session.flush()  # obtain msg.id

    session.add(
        TokenAudit(
            user_id=user.id,
            message_id=msg.id,
            conversation_id=conversation_id,
            role=role,
            content_type=content_type,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
    )
    conv = await session.get(Conversation, conversation_id)
    if conv:
        conv.last_message_at = func.now()
    await session.commit()
    return msg


async def get_context(session: AsyncSession, user: User) -> list[dict]:
    """Last N text messages of the ACTIVE conversation (oldest -> newest)."""
    conv = await get_active_conversation(session, user)
    result = await session.execute(
        select(Message)
        .where(
            Message.conversation_id == conv.id,
            Message.role.in_(["user", "assistant"]),
            Message.content_type == "text",
        )
        .order_by(desc(Message.created_at))
        .limit(settings.context_messages)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return [{"role": m.role, "content": m.content} for m in rows]


# ─────────────────────────── Tags & memory ───────────────────────────

async def add_user_tag(
    session: AsyncSession, user_id: int, tag: str, *, source: str = "admin", note: str | None = None
) -> bool:
    existing = await session.execute(
        select(UserTag).where(UserTag.user_id == user_id, UserTag.tag == tag)
    )
    if existing.scalar_one_or_none():
        return False
    session.add(UserTag(user_id=user_id, tag=tag, source=source, note=note))
    await session.commit()
    return True


async def remove_user_tag(session: AsyncSession, user_id: int, tag: str) -> bool:
    result = await session.execute(
        select(UserTag).where(UserTag.user_id == user_id, UserTag.tag == tag)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        return False
    await session.delete(obj)
    await session.commit()
    return True


async def list_user_tags(session: AsyncSession, user_id: int) -> list[UserTag]:
    result = await session.execute(
        select(UserTag).where(UserTag.user_id == user_id).order_by(UserTag.created_at)
    )
    return list(result.scalars().all())


async def add_user_memory(
    session: AsyncSession, user_id: int, content: str, *,
    vector_id: str | None = None, conversation_id: int | None = None, kind: str = "message",
) -> None:
    session.add(
        UserMemory(
            user_id=user_id, content=content, vector_id=vector_id,
            conversation_id=conversation_id, kind=kind,
        )
    )
    await session.commit()


async def count_user_messages(session: AsyncSession, user_id: int) -> int:
    return await session.scalar(
        select(func.count(TokenAudit.id)).where(
            TokenAudit.user_id == user_id, TokenAudit.role == "user"
        )
    ) or 0


async def count_used_conversations(session: AsyncSession, user_id: int) -> int:
    """Conversations the user has actually sent messages in."""
    return await session.scalar(
        select(func.count(func.distinct(Message.conversation_id))).where(
            Message.user_id == user_id
        )
    ) or 0


async def set_user_segment(session: AsyncSession, user_id: int, segment: str) -> None:
    user = await session.get(User, user_id)
    if user:
        user.segment = segment
        await session.commit()


async def mark_segment_notified(session: AsyncSession, user_id: int, value: str) -> None:
    user = await session.get(User, user_id)
    if user:
        user.segment_notified = value
        await session.commit()


async def recent_user_messages_text(session: AsyncSession, user_id: int, limit: int = 15) -> str:
    result = await session.execute(
        select(Message.content)
        .where(Message.user_id == user_id, Message.role == "user")
        .order_by(desc(Message.created_at))
        .limit(limit)
    )
    return "\n".join(result.scalars().all())


# ───────────────────── Per-user usage (computed from facts) ─────────────────

async def user_usage(session: AsyncSession, user_id: int) -> dict:
    row = (
        await session.execute(
            select(
                func.count(TokenAudit.id),
                func.coalesce(func.sum(TokenAudit.total_tokens), 0),
                func.coalesce(func.sum(TokenAudit.prompt_tokens), 0),
                func.coalesce(func.sum(TokenAudit.completion_tokens), 0),
            ).where(TokenAudit.user_id == user_id)
        )
    ).one()
    images = await session.scalar(
        select(func.count(TokenAudit.id)).where(
            TokenAudit.user_id == user_id, TokenAudit.content_type == "image"
        )
    )
    return {
        "messages": row[0] or 0,
        "total_tokens": row[1] or 0,
        "prompt_tokens": row[2] or 0,
        "completion_tokens": row[3] or 0,
        "images": images or 0,
    }


# ───────────────────────────── Admin / stats ─────────────────────────────

async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def set_banned(session: AsyncSession, telegram_id: int, banned: bool) -> bool:
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        return False
    user.is_banned = banned
    await session.commit()
    return True


async def all_user_ids(session: AsyncSession) -> list[int]:
    # Only users who actually started the bot can be messaged (and not banned).
    result = await session.execute(
        select(User.telegram_id).where(
            User.is_banned == False, User.is_active == True  # noqa: E712
        )
    )
    return [r for r in result.scalars().all()]


async def log_broadcast(session: AsyncSession, text: str, sent: int, failed: int) -> None:
    session.add(BroadcastLog(text=text, sent_count=sent, failed_count=failed))
    await session.commit()


async def log_web_search(
    session: AsyncSession, user_id: int, query: str, answer: str | None, sources: list
) -> None:
    session.add(
        WebSearch(
            user_id=user_id,
            query=query,
            answer=answer,
            sources=sources,
            result_count=len(sources or []),
        )
    )
    await session.commit()


async def get_stats(session: AsyncSession) -> dict:
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    total_users = await session.scalar(select(func.count(User.id)))
    started_users = await session.scalar(
        select(func.count(User.id)).where(User.is_active == True)  # noqa: E712
    )
    banned_users = await session.scalar(select(func.count(User.id)).where(User.is_banned == True))  # noqa: E712
    active_24h = await session.scalar(
        select(func.count(User.id)).where(User.last_active >= day_ago)
    )
    new_24h = await session.scalar(select(func.count(User.id)).where(User.created_at >= day_ago))
    new_7d = await session.scalar(select(func.count(User.id)).where(User.created_at >= week_ago))
    total_messages = await session.scalar(select(func.count(TokenAudit.id)))
    total_tokens = await session.scalar(select(func.coalesce(func.sum(TokenAudit.total_tokens), 0)))
    total_images = await session.scalar(
        select(func.count(TokenAudit.id)).where(TokenAudit.content_type == "image")
    )

    return {
        "total_users": total_users or 0,
        "started_users": started_users or 0,
        "banned_users": banned_users or 0,
        "active_24h": active_24h or 0,
        "new_24h": new_24h or 0,
        "new_7d": new_7d or 0,
        "total_messages": total_messages or 0,
        "total_tokens": total_tokens or 0,
        "total_images": total_images or 0,
    }


async def list_users(session: AsyncSession, limit: int = 100, offset: int = 0) -> list[User]:
    result = await session.execute(
        select(User).order_by(desc(User.last_active)).limit(limit).offset(offset)
    )
    return list(result.scalars().all())


async def list_top_users(session: AsyncSession, limit: int = 10) -> list[tuple[User, int, int]]:
    """Top users by activity → (user, message_count, total_tokens)."""
    rows = await session.execute(
        select(
            User,
            func.count(TokenAudit.id).label("msgs"),
            func.coalesce(func.sum(TokenAudit.total_tokens), 0).label("tokens"),
        )
        .join(TokenAudit, TokenAudit.user_id == User.id)
        .group_by(User.id)
        .order_by(desc("msgs"))
        .limit(limit)
    )
    return [(u, int(m), int(t)) for u, m, t in rows.all()]


async def find_user_by_username(session: AsyncSession, username: str) -> User | None:
    username = username.lstrip("@")
    result = await session.execute(select(User).where(func.lower(User.username) == username.lower()))
    return result.scalar_one_or_none()
