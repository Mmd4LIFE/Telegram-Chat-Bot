"""Database access helpers (star-schema aware)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    BroadcastLog,
    Message,
    ModelSelection,
    TokenAudit,
    User,
)


async def get_or_create_user(session: AsyncSession, tg_user) -> User:
    """Fetch a user by telegram id, creating/refreshing their profile."""
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
            is_admin=is_admin,
        )
        session.add(user)
        await session.flush()
        # seed the initial model selection so the user has a "current" model
        session.add(ModelSelection(user_id=user.id, model=settings.default_model))
        await session.commit()
        await session.refresh(user)
        return user

    user.username = tg_user.username
    user.first_name = tg_user.first_name
    user.last_name = tg_user.last_name
    user.language_code = tg_user.language_code
    user.is_premium = bool(getattr(tg_user, "is_premium", False))
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
) -> Message:
    """Persist conversation content (messages) AND a durable token audit row."""
    msg = Message(
        user_id=user.id,
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
            role=role,
            content_type=content_type,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
    )
    await session.commit()
    return msg


async def get_context(session: AsyncSession, user: User) -> list[dict]:
    """Last N text messages as OpenAI chat history (oldest -> newest)."""
    result = await session.execute(
        select(Message)
        .where(
            Message.user_id == user.id,
            Message.role.in_(["user", "assistant"]),
            Message.content_type == "text",
        )
        .order_by(desc(Message.created_at))
        .limit(settings.context_messages)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return [{"role": m.role, "content": m.content} for m in rows]


async def clear_context(session: AsyncSession, user: User) -> int:
    """Delete a user's messages so context starts fresh.

    Token audits persist (their message_id is set NULL by the FK), so usage
    history is preserved.
    """
    result = await session.execute(select(Message).where(Message.user_id == user.id))
    msgs = result.scalars().all()
    count = len(msgs)
    for m in msgs:
        await session.delete(m)
    await session.commit()
    return count


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
    result = await session.execute(select(User.telegram_id).where(User.is_banned == False))  # noqa: E712
    return [r for r in result.scalars().all()]


async def log_broadcast(session: AsyncSession, text: str, sent: int, failed: int) -> None:
    session.add(BroadcastLog(text=text, sent_count=sent, failed_count=failed))
    await session.commit()


async def get_stats(session: AsyncSession) -> dict:
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    total_users = await session.scalar(select(func.count(User.id)))
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
