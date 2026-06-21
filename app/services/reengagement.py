"""Proactive re-engagement.

A background scheduler periodically finds conversations that are still open but
whose user has been silent for `reengage_inactivity_hours`. For each, it:
  1. titles & closes the stale conversation,
  2. opens a fresh conversation,
  3. sends the user a short, persona-aware follow-up question that references
     their previous conversation(s) — to pull them back in.

Only active (started, non-banned) users with at least one prior user message are
targeted, so we never message group-only members nor nag an ignored ping.
"""
from __future__ import annotations

import asyncio

from app.bot import keyboards as kb
from app.bot.bot import bot
from app.bot.formatting import to_telegram_html
from app.config import settings
from app.database import SessionLocal
from app.logger import get_logger
from app.services import crud
from app.services.openai_service import generate_reengagement, summarize_title

log = get_logger(__name__)


async def _reengage_one(conv_id: int, telegram_id: int) -> bool:
    # Gather context from the stale conversation.
    async with SessionLocal() as session:
        transcript = await crud.conversation_transcript(session, conv_id, limit=20)
        user = await crud.get_user_by_telegram_id(session, telegram_id)
        if not user:
            return False
        persona, segment, is_admin = user.system_prompt, user.segment, user.is_admin

    if not transcript.strip():
        return False

    try:
        title = await summarize_title(transcript)
    except Exception:  # noqa: BLE001
        title = "Previous chat"
    question = await generate_reengagement(transcript, persona, segment)
    if not question:
        return False

    # Close the stale conversation, open a fresh one, store the bot's opener.
    async with SessionLocal() as session:
        user = await crud.get_user_by_telegram_id(session, telegram_id)
        await crud.set_conversation_title(session, conv_id, title)
        new_conv = await crud.start_new_conversation(session, user)
        await crud.save_message(
            session, user, "assistant", question,
            model="reengage", conversation_id=new_conv.id,
        )

    await bot.send_message(
        telegram_id, to_telegram_html(question), reply_markup=kb.main_menu(is_admin)
    )
    return True


async def run_once() -> int:
    """One sweep. Returns how many users were re-engaged."""
    if not settings.reengage_enabled:
        return 0
    async with SessionLocal() as session:
        candidates = await crud.stale_active_conversations(
            session, settings.reengage_inactivity_hours, settings.reengage_max_per_run
        )
    count = 0
    for conv, user in candidates:
        try:
            if await _reengage_one(conv.id, user.telegram_id):
                count += 1
            await asyncio.sleep(0.1)  # gentle pacing for Telegram + OpenAI
        except Exception:  # noqa: BLE001
            log.exception("re-engagement failed for user %s", user.telegram_id)
    if count:
        log.info("Re-engaged %s idle user(s).", count)
    return count


async def run_scheduler() -> None:
    """Background loop — runs forever until cancelled on shutdown."""
    await asyncio.sleep(60)  # let startup settle
    interval = max(1, settings.reengage_check_minutes) * 60
    while True:
        try:
            await run_once()
        except Exception:  # noqa: BLE001
            log.exception("re-engagement sweep error")
        await asyncio.sleep(interval)
