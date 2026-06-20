"""Main bot message & callback handlers."""
from __future__ import annotations

import logging
import os
import tempfile

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Contact, Message as TgMessage

from app.bot import keyboards as kb
from app.bot.bot import bot, send_long
from app.bot.texts import BANNED, HELP, WELCOME
from app.database import SessionLocal
from app.services import crud
from app.services.openai_service import (
    IMAGE_MODEL,
    chat_completion,
    generate_image,
    get_model_label,
    transcribe_voice,
    vision_completion,
)

log = logging.getLogger(__name__)
router = Router()


async def _load_user(tg_user):
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, tg_user)
        return user


# ─────────────────────────── Commands ───────────────────────────

@router.message(CommandStart())
async def cmd_start(message: TgMessage):
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        if user.is_banned:
            return await message.answer(BANNED)
    await message.answer(WELCOME, reply_markup=kb.main_menu(user.is_admin))


@router.message(Command("help"))
@router.message(F.text == kb.BTN_HELP)
async def cmd_help(message: TgMessage):
    await message.answer(HELP, reply_markup=kb.main_menu(message.from_user.id == _admin_id()))


@router.message(Command("new"))
@router.message(F.text == kb.BTN_NEW_CHAT)
async def cmd_new(message: TgMessage):
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        n = await crud.clear_context(session, user)
    await message.answer(
        f"🆕 <b>Fresh start!</b> Cleared {n} messages from memory.\nWhat would you like to talk about?",
        reply_markup=kb.main_menu(user.is_admin),
    )


@router.message(Command("models"))
@router.message(F.text == kb.BTN_MODELS)
async def cmd_models(message: TgMessage):
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
    await message.answer(
        f"🤖 <b>Choose your AI model</b>\nCurrent: {get_model_label(user.selected_model)}",
        reply_markup=kb.models_kb(user.selected_model),
    )


@router.message(F.text == kb.BTN_IMAGE)
async def cmd_image_mode(message: TgMessage):
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        await crud.set_model(session, user, IMAGE_MODEL)
    await message.answer(
        "🎨 <b>Image mode ON</b> (DALL·E 3)\nSend me a description and I'll create an image.\n"
        "<i>Switch back anytime via 🤖 Models.</i>",
        reply_markup=kb.main_menu(user.is_admin),
    )


@router.message(F.text == kb.BTN_PERSONA)
async def cmd_persona(message: TgMessage):
    await message.answer("🎭 <b>Pick a persona</b> for the assistant:", reply_markup=kb.persona_kb())


@router.message(Command("stats"))
@router.message(F.text == kb.BTN_STATS)
async def cmd_stats(message: TgMessage):
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
    txt = (
        "📊 <b>Your stats</b>\n\n"
        f"🤖 Model: {get_model_label(user.selected_model)}\n"
        f"💬 Messages: <b>{user.message_count}</b>\n"
        f"🎨 Images: <b>{user.image_count}</b>\n"
        f"🔢 Tokens used: <b>{user.total_tokens:,}</b>\n"
        f"📅 Member since: {user.created_at:%Y-%m-%d}"
    )
    await message.answer(txt, reply_markup=kb.main_menu(user.is_admin))


# ───────────────────────── Contact / phone ──────────────────────

@router.message(F.contact)
async def on_contact(message: TgMessage):
    contact: Contact = message.contact
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        if contact.user_id == message.from_user.id:
            await crud.set_phone(session, user, contact.phone_number)
    await message.answer("✅ Thanks! Saved.", reply_markup=kb.main_menu(user.is_admin))


@router.message(F.text == "⏭ Skip")
async def on_skip(message: TgMessage):
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
    await message.answer("👍 No problem.", reply_markup=kb.main_menu(user.is_admin))


# ─────────────────────────── Callbacks ──────────────────────────

@router.callback_query(F.data.startswith("model:"))
async def cb_model(call: CallbackQuery):
    model = call.data.split(":", 1)[1]
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, call.from_user)
        await crud.set_model(session, user, model)
    await call.answer(f"Switched to {get_model_label(model)}")
    try:
        await call.message.edit_text(
            f"✅ <b>Model set:</b> {get_model_label(model)}\n"
            + ("Send a description to generate an image." if model == IMAGE_MODEL else "Ask me anything!"),
        )
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("persona:"))
async def cb_persona(call: CallbackQuery):
    idx = int(call.data.split(":", 1)[1])
    prompt = kb.PERSONAS[idx] if 0 <= idx < len(kb.PERSONAS) else ""
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, call.from_user)
        await crud.set_system_prompt(session, user, prompt or None)
    await call.answer("Persona updated")
    label = "Default assistant" if not prompt else prompt[:60] + "…"
    try:
        await call.message.edit_text(f"🎭 <b>Persona set.</b>\n<i>{label}</i>")
    except Exception:  # noqa: BLE001
        pass


# ───────────────────────── Media handlers ───────────────────────

@router.message(F.photo)
async def on_photo(message: TgMessage):
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        if user.is_banned:
            return await message.answer(BANNED)

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
    caption = message.caption or "Describe this image in detail."

    try:
        result = await vision_completion(user.selected_model, caption, file_url)
    except Exception as e:  # noqa: BLE001
        log.exception("vision error")
        return await message.answer(f"⚠️ Could not analyse the image: {e}")

    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        await crud.save_message(session, user, "user", f"[photo] {caption}", content_type="image")
        await crud.save_message(
            session, user, "assistant", result.text, model=result.model,
            prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
        )
    await send_long(message.chat.id, result.text, reply_markup=kb.main_menu(user.is_admin))


@router.message(F.voice | F.audio)
async def on_voice(message: TgMessage):
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        if user.is_banned:
            return await message.answer(BANNED)

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    voice = message.voice or message.audio
    file = await bot.get_file(voice.file_id)

    tmp_path = None
    try:
        suffix = os.path.splitext(file.file_path)[1] or ".oga"
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        await bot.download_file(file.file_path, tmp_path)
        text = await transcribe_voice(tmp_path)
    except Exception as e:  # noqa: BLE001
        log.exception("voice error")
        return await message.answer(f"⚠️ Could not transcribe audio: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    await message.answer(f"🎙 <i>You said:</i> {text}")
    await _handle_chat(message, text, user_prefix="[voice] ")


# ───────────────────────── Main chat / catch-all ────────────────

@router.message(F.text)
async def on_text(message: TgMessage):
    await _handle_chat(message, message.text)


async def _handle_chat(message: TgMessage, text: str, user_prefix: str = ""):
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        if user.is_banned:
            return await message.answer(BANNED)
        model = user.selected_model
        system_prompt = user.system_prompt
        is_admin = user.is_admin

    # Image generation mode
    if model == IMAGE_MODEL:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
        try:
            url = await generate_image(text)
        except Exception as e:  # noqa: BLE001
            log.exception("image gen error")
            return await message.answer(f"⚠️ Image generation failed: {e}")
        async with SessionLocal() as session:
            user = await crud.get_or_create_user(session, message.from_user)
            await crud.save_message(session, user, "user", f"{user_prefix}{text}", content_type="text")
            await crud.save_message(session, user, "assistant", url, content_type="image", model=IMAGE_MODEL)
        return await message.answer_photo(url, caption=f"🎨 <i>{text[:200]}</i>")

    # Chat mode
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        await crud.save_message(session, user, "user", f"{user_prefix}{text}")
        context = await crud.get_context(session, user)

    try:
        result = await chat_completion(model, context, system_prompt)
    except Exception as e:  # noqa: BLE001
        log.exception("chat error")
        return await message.answer(
            f"⚠️ The model <b>{model}</b> returned an error:\n<code>{e}</code>\n\n"
            "Try another model via 🤖 Models."
        )

    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        await crud.save_message(
            session, user, "assistant", result.text, model=result.model,
            prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
        )
    await send_long(message.chat.id, result.text, reply_markup=kb.main_menu(is_admin))


def _admin_id() -> int:
    from app.config import settings
    return settings.admin_telegram_id
