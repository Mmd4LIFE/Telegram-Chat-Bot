"""Group logger.

When the bot is in a group (privacy mode disabled in BotFather), every message
of every type is captured for per-user personalization:
  • text/caption  → stored + emojis counted + embedded into the vector memory
  • voice/video_note → downloaded, transcribed with Whisper, then treated as text
  • sticker → emoji + file_id stored (so we can echo the user's own sticker back)
  • photo/video/animation/document/… → logged with type + caption

All work is best-effort: a failure on one message never affects the group.
"""
from __future__ import annotations

import os
import re
import tempfile

from aiogram import F, Router
from aiogram.types import ChatMemberUpdated, Message as TgMessage

from app.bot.bot import bot
from app.bot.formatting import to_telegram_html
from app.database import SessionLocal
from app.logger import get_logger
from app.services import crud, group_crud, vector_service
from app.services.openai_service import express_user, transcribe_voice
from app.utils.emoji import extract_emojis

log = get_logger(__name__)
router = Router()

# Only handle messages that come from groups / supergroups.
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

# Cache chat_id -> internal group id to avoid a DB lookup on every message.
_group_cache: dict[int, int] = {}
_bot_username: str | None = None

MAX_TRANSCRIBE_SECONDS = 120  # don't transcribe very long audio (cost control)


async def _bot_uname() -> str:
    global _bot_username
    if _bot_username is None:
        _bot_username = (await bot.get_me()).username or ""
    return _bot_username


_LANG_RE = re.compile(r"\bin\s+([A-Za-z؀-ۿ]+)", re.IGNORECASE)


async def _try_express(message: TgMessage) -> bool:
    """Handle: 'Hey @bot, express @user [in <language>]'. Returns True if handled."""
    text = message.text or ""
    if "express" not in text.lower():
        return False
    botname = await _bot_uname()
    mentions = re.findall(r"@(\w+)", text)
    if botname and botname.lower() not in [m.lower() for m in mentions]:
        return False  # the bot must be addressed

    # Resolve the target: a text_mention (user w/o username) wins, else an @handle.
    text_mention_user = next(
        (e.user for e in (message.entities or []) if e.type == "text_mention" and e.user), None
    )
    targets = [m for m in mentions if m.lower() != (botname or "").lower()]

    # Requested output language.
    language = None
    m = _LANG_RE.search(text)
    if m:
        language = m.group(1)
    if "فارسی" in text or "پارسی" in text:
        language = "Persian"

    async with SessionLocal() as session:
        if text_mention_user:
            target = await crud.get_user_by_telegram_id(session, text_mention_user.id)
            display = "@" + (text_mention_user.username or text_mention_user.first_name or "user")
        elif targets:
            target = await crud.find_user_by_username(session, targets[0])
            display = "@" + targets[0]
        else:
            return False
        if not target:
            await bot.send_message(message.chat.id, f"🤔 I don't have any data on {display} yet.")
            return True
        display = f"@{target.username}" if target.username else target.full_name
        profile = await group_crud.user_group_profile(session, target.id)

    if not profile:
        await bot.send_message(
            message.chat.id, f"🤷 I haven't seen {display} say much in groups yet."
        )
        return True

    await bot.send_chat_action(message.chat.id, "typing")
    try:
        expose = await express_user(display, profile, language)
    except Exception:  # noqa: BLE001
        log.exception("express generation failed")
        return True
    await bot.send_message(message.chat.id, to_telegram_html(expose))
    if profile.get("sticker_file_id"):
        try:
            await bot.send_sticker(message.chat.id, profile["sticker_file_id"])
        except Exception:  # noqa: BLE001
            pass
    return True


async def _group_id(chat) -> int:
    gid = _group_cache.get(chat.id)
    if gid is not None:
        return gid
    async with SessionLocal() as session:
        group = await group_crud.register_group(session, chat)
        _group_cache[chat.id] = group.id
        return group.id


# ───────────────────────── Membership events ─────────────────────────

@router.my_chat_member()
async def on_my_membership(event: ChatMemberUpdated):
    status = event.new_chat_member.status
    chat = event.chat
    if chat.type not in {"group", "supergroup"}:
        return
    if status in {"member", "administrator"}:
        async with SessionLocal() as session:
            group = await group_crud.register_group(session, chat)
            _group_cache[chat.id] = group.id
        log.info("Added to group %s (%s)", chat.title, chat.id)
        try:
            await bot.send_message(
                chat.id,
                "👋 Hi! I'm now active here. To personalize answers for each member "
                "I read messages in this group. Mention me or DM me to chat 1-on-1.",
            )
        except Exception:  # noqa: BLE001
            pass
    elif status in {"left", "kicked"}:
        _group_cache.pop(chat.id, None)
        async with SessionLocal() as session:
            await group_crud.set_group_active(session, chat.id, False)
        log.info("Removed from group %s (%s)", chat.title, chat.id)


# ───────────────────────── Message capture ─────────────────────────

def _classify(message: TgMessage):
    """Return (message_type, text, file_id, sticker_emoji, duration)."""
    if message.text is not None:
        return "text", message.text, None, None, None
    if message.sticker:
        return "sticker", None, message.sticker.file_id, message.sticker.emoji, None
    if message.voice:
        return "voice", message.caption, message.voice.file_id, None, message.voice.duration
    if message.video_note:
        return "video_note", None, message.video_note.file_id, None, message.video_note.duration
    if message.audio:
        return "audio", message.caption, message.audio.file_id, None, message.audio.duration
    if message.photo:
        return "photo", message.caption, message.photo[-1].file_id, None, None
    if message.video:
        return "video", message.caption, message.video.file_id, None, message.video.duration
    if message.animation:
        return "animation", message.caption, message.animation.file_id, None, None
    if message.document:
        return "document", message.caption, message.document.file_id, None, None
    if message.poll:
        return "poll", message.poll.question, None, None, None
    if message.location:
        return "location", None, None, None, None
    if message.contact:
        return "contact", message.contact.phone_number, None, None, None
    return "other", message.caption, None, None, None


@router.message()
async def on_group_message(message: TgMessage):
    if message.from_user is None or message.from_user.is_bot:
        return  # ignore service messages and other bots

    # "Hey @bot, express @user" — handle and skip logging the command itself.
    try:
        if message.text and await _try_express(message):
            return
    except Exception:  # noqa: BLE001
        log.exception("express handler error")

    try:
        group_id = await _group_id(message.chat)
        mtype, text, file_id, sticker_emoji, duration = _classify(message)
        tg = message.from_user

        # Force-create the sender as a NON-active user (they haven't started the
        # bot yet). This gives every group member an internal id immediately, so
        # emoji stats and vector memory work right away; they're promoted to
        # active once they DM the bot.
        async with SessionLocal() as session:
            user = await crud.get_or_create_user(session, tg, active=False)
            user_id = user.id

        # Voice / round-video → transcribe (best-effort, length-capped).
        transcription = None
        if mtype in {"voice", "video_note", "audio"} and duration and duration <= MAX_TRANSCRIBE_SECONDS:
            transcription = await _transcribe(file_id)

        # Emojis from text/caption + the sticker itself.
        emoji_list = extract_emojis(text)
        if sticker_emoji:
            emoji_list.append(sticker_emoji)

        async with SessionLocal() as session:
            await group_crud.save_group_message(
                session, group_id,
                telegram_user_id=tg.id,
                username=tg.username,
                first_name=tg.first_name,
                user_id=user_id,
                telegram_message_id=message.message_id,
                message_type=mtype,
                text=text,
                transcription=transcription,
                emojis="".join(emoji_list) or None,
                sticker_emoji=sticker_emoji,
                file_id=file_id,
                duration=duration,
            )
            if emoji_list:
                await group_crud.increment_emojis(session, user_id, emoji_list)

        learn_text = transcription or (text if mtype == "text" else None)
        if learn_text and len(learn_text.strip()) >= 8:
            vid = await vector_service.remember(user_id, learn_text, role="group")
            async with SessionLocal() as session:
                await crud.add_user_memory(session, user_id, learn_text, vector_id=vid, kind="group")
    except Exception:  # noqa: BLE001
        log.exception("group message capture failed")


async def _transcribe(file_id: str) -> str | None:
    tmp = None
    try:
        f = await bot.get_file(file_id)
        suffix = os.path.splitext(f.file_path)[1] or ".oga"
        fd, tmp = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        await bot.download_file(f.file_path, tmp)
        return await transcribe_voice(tmp)
    except Exception:  # noqa: BLE001
        log.warning("group voice transcription failed")
        return None
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
