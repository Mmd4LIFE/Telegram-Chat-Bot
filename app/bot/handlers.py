"""Main bot message & callback handlers."""
from __future__ import annotations

import asyncio
import html
import io
import logging
import os
import tempfile

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Contact, Message as TgMessage

from app.bot import keyboards as kb
from app.bot.bot import bot, send_long
from app.bot.formatting import to_telegram_html
from app.bot.texts import BANNED, HELP, WELCOME
from app.config import settings
from app.database import SessionLocal
from app.services import crud, vector_service
from app.services.openai_service import (
    IMAGE_MODEL,
    chat_completion,
    classify_tags,
    edit_image,
    generate_image,
    get_model_label,
    summarize_title,
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
async def cmd_new(message: TgMessage, state: FSMContext):
    await state.clear()
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        old = await crud.get_active_conversation(session, user)
        await _maybe_title(session, old.id)            # recap the chat we're leaving
        await crud.start_new_conversation(session, user)
        await crud.set_model(session, user, settings.default_model)  # back to default model
    await message.answer(
        "🆕 <b>New chat started.</b> Your previous chat was saved to 📜 History.\n"
        f"🤖 Model reset to {get_model_label(settings.default_model)}.\n"
        "What would you like to talk about?",
        reply_markup=kb.main_menu(user.is_admin),
    )


async def _maybe_title(session, conversation_id: int) -> None:
    """Generate a short recap title for a conversation if it has content."""
    from app.models import Conversation

    conv = await session.get(Conversation, conversation_id)
    if not conv or conv.title:
        return
    transcript = await crud.conversation_transcript(session, conversation_id)
    if not transcript.strip():
        return
    try:
        title = await summarize_title(transcript)
    except Exception:  # noqa: BLE001
        title = transcript.split("\n", 1)[0][6:46] or "Chat"
    await crud.set_conversation_title(session, conversation_id, title or "Chat")


@router.message(Command("history"))
@router.message(F.text == kb.BTN_HISTORY)
async def cmd_history(message: TgMessage):
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        # ensure the active chat has a recap before showing the list
        active = await crud.get_active_conversation(session, user)
        await _maybe_title(session, active.id)
        items = await crud.list_conversations(session, user, limit=10)
    if not items:
        return await message.answer(
            "📜 You have no past conversations yet — start chatting!",
            reply_markup=kb.main_menu(user.is_admin),
        )
    await message.answer(
        "📜 <b>Your conversations</b>\nTap one to resume it:",
        reply_markup=kb.conversations_kb(items),
    )


@router.callback_query(F.data == "conv:new")
async def cb_conv_new(call: CallbackQuery, state: FSMContext):
    await state.clear()
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, call.from_user)
        old = await crud.get_active_conversation(session, user)
        await _maybe_title(session, old.id)
        await crud.start_new_conversation(session, user)
        await crud.set_model(session, user, settings.default_model)
    await call.answer("New chat started")
    try:
        await call.message.edit_text("🆕 <b>New chat started.</b> Ask me anything!")
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("conv:"))
async def cb_conv_open(call: CallbackQuery):
    conv_id = int(call.data.split(":", 1)[1])
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, call.from_user)
        conv = await crud.set_active_conversation(session, user, conv_id)
    if not conv:
        return await call.answer("Conversation not found", show_alert=True)
    await call.answer("Resumed")
    title = conv.title or "this chat"
    try:
        await call.message.edit_text(
            f"↩️ <b>Resumed:</b> {title}\nContinue where you left off — I remember the context."
        )
    except Exception:  # noqa: BLE001
        pass


@router.message(Command("models"))
@router.message(F.text == kb.BTN_MODELS)
async def cmd_models(message: TgMessage):
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        current = await crud.get_current_model(session, user)
    await message.answer(
        f"🤖 <b>Choose your AI model</b>\nCurrent: {get_model_label(current)}",
        reply_markup=kb.models_kb(current),
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
        current = await crud.get_current_model(session, user)
        usage = await crud.user_usage(session, user.id)
    txt = (
        "📊 <b>Your stats</b>\n\n"
        f"🤖 Model: {get_model_label(current)}\n"
        f"💬 Messages: <b>{usage['messages']}</b>\n"
        f"🎨 Images: <b>{usage['images']}</b>\n"
        f"🔢 Tokens used: <b>{usage['total_tokens']:,}</b>\n"
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
async def on_photo(message: TgMessage, state: FSMContext):
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        if user.is_banned:
            return await message.answer(BANNED)

    photo = message.photo[-1]
    caption = message.caption

    # No caption → just describe it (classic vision behaviour).
    if not caption:
        return await _describe_photo(message.chat.id, message.from_user, photo.file_id,
                                     "Describe this image in detail.")

    # Captioned → let the user choose: transform the image or describe it.
    await state.update_data(img_file_id=photo.file_id, img_caption=caption)
    await message.answer(
        "🖼 <b>What should I do with this image?</b>\n\n"
        "🎨 <b>Transform / Edit</b> — redraw it following your prompt\n"
        "👁 <b>Describe it</b> — explain what's in the picture",
        reply_markup=kb.photo_action_kb(),
    )


async def _describe_photo(chat_id: int, tg_user, file_id: str, prompt: str):
    await bot.send_chat_action(chat_id, ChatAction.TYPING)
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, tg_user)
        model = await crud.get_current_model(session, user)
        is_admin = user.is_admin

    file = await bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
    try:
        result = await vision_completion(model, prompt, file_url)
    except Exception as e:  # noqa: BLE001
        log.exception("vision error")
        return await bot.send_message(chat_id, f"⚠️ Could not analyse the image: {e}")

    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, tg_user)
        await crud.save_message(session, user, "user", f"[photo] {prompt}", content_type="image")
        await crud.save_message(
            session, user, "assistant", result.text, model=result.model,
            prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
        )
    await send_long(chat_id, to_telegram_html(result.text), reply_markup=kb.main_menu(is_admin))


async def _edit_photo(chat_id: int, tg_user, file_id: str, prompt: str):
    await bot.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)
    file = await bot.get_file(file_id)
    buf = await bot.download_file(file.file_path)
    image_bytes = buf.read()

    try:
        result = await edit_image(prompt, image_bytes, filename="photo.jpg", content_type="image/jpeg")
    except Exception as e:  # noqa: BLE001
        log.exception("image edit error")
        return await bot.send_message(chat_id, f"⚠️ Image transformation failed: {e}")

    photo = result.url if result.kind == "url" else BufferedInputFile(result.data, "edited.png")
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, tg_user)
        is_admin = user.is_admin
        await crud.save_message(session, user, "user", f"[photo edit] {prompt}", content_type="image")
        await crud.save_message(
            session, user, "assistant", result.url or "[edited image]",
            content_type="image", model=result.model,
        )
    await bot.send_photo(
        chat_id,
        photo,
        caption=f"🎨 <i>{html.escape(prompt[:180])}</i>",
        reply_markup=kb.main_menu(is_admin),
    )


@router.callback_query(F.data == "img:edit")
async def cb_img_edit(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    file_id, prompt = data.get("img_file_id"), data.get("img_caption")
    if not file_id:
        return await call.answer("This image expired — please send it again.", show_alert=True)
    await call.answer()
    await state.update_data(img_file_id=None, img_caption=None)
    try:
        await call.message.edit_text("🎨 <b>Transforming your image…</b> this can take ~20–40s ⏳")
    except Exception:  # noqa: BLE001
        pass
    await _edit_photo(call.message.chat.id, call.from_user, file_id, prompt)


@router.callback_query(F.data == "img:describe")
async def cb_img_describe(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    file_id, prompt = data.get("img_file_id"), data.get("img_caption")
    if not file_id:
        return await call.answer("This image expired — please send it again.", show_alert=True)
    await call.answer()
    await state.update_data(img_file_id=None, img_caption=None)
    try:
        await call.message.edit_text("👁 <b>Analysing the image…</b>")
    except Exception:  # noqa: BLE001
        pass
    await _describe_photo(call.message.chat.id, call.from_user, file_id, prompt)


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
        model = await crud.get_current_model(session, user)
        system_prompt = user.system_prompt
        is_admin = user.is_admin

    # Image generation mode
    if model == IMAGE_MODEL:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
        try:
            image = await generate_image(text)
        except Exception as e:  # noqa: BLE001
            log.exception("image gen error")
            return await message.answer(f"⚠️ Image generation failed: {e}")

        photo = image.url if image.kind == "url" else BufferedInputFile(image.data, "image.png")
        caption = f"🎨 <i>{html.escape(text[:200])}</i>"
        stored = image.url or "[generated image]"
        async with SessionLocal() as session:
            user = await crud.get_or_create_user(session, message.from_user)
            await crud.save_message(session, user, "user", f"{user_prefix}{text}", content_type="text")
            await crud.save_message(
                session, user, "assistant", stored, content_type="image", model=image.model
            )
        return await message.answer_photo(photo, caption=caption)

    # Chat mode
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user)
        conv = await crud.get_active_conversation(session, user)
        user_id, conv_id = user.id, conv.id
        await crud.save_message(session, user, "user", f"{user_prefix}{text}", conversation_id=conv_id)
        context = await crud.get_context(session, user)
        tags = [t.tag for t in await crud.list_user_tags(session, user.id)]

    # ── Personalization: recall relevant memories from the vector engine ──
    memories = await vector_service.recall(user_id, text)
    augmented_prompt = _build_personalized_prompt(system_prompt, memories, tags)

    try:
        result = await chat_completion(model, context, augmented_prompt)
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
            total_tokens=result.total_tokens, conversation_id=conv_id,
        )
    await send_long(message.chat.id, to_telegram_html(result.text), reply_markup=kb.main_menu(is_admin))

    # ── Learn from this turn in the background (never blocks the reply) ──
    asyncio.create_task(_learn_from_turn(user_id, conv_id, text))


def _build_personalized_prompt(system_prompt: str | None, memories: list[str], tags: list[str]) -> str:
    parts: list[str] = []
    if system_prompt:
        parts.append(system_prompt)
    if tags:
        parts.append("User segmentation tags: " + ", ".join(tags) + ".")
    if memories:
        parts.append(
            "What you remember about this user (use it to personalize, do not mention it):\n- "
            + "\n- ".join(memories)
        )
    return "\n\n".join(parts) if parts else None


async def _learn_from_turn(user_id: int, conv_id: int, text: str) -> None:
    """Store this user message as personalization memory + occasionally re-tag."""
    try:
        vid = await vector_service.remember(user_id, text, conversation_id=conv_id, role="user")
        async with SessionLocal() as session:
            await crud.add_user_memory(
                session, user_id, text, vector_id=vid, conversation_id=conv_id, kind="message"
            )
            count = await crud.count_user_messages(session, user_id)
            # Re-segment the user every 8 messages.
            if count and count % 8 == 0:
                transcript = await crud.recent_user_messages_text(session, user_id)
                try:
                    suggested = await classify_tags(transcript)
                except Exception:  # noqa: BLE001
                    suggested = []
                for tag in suggested:
                    await crud.add_user_tag(session, user_id, tag, source="auto")
    except Exception:  # noqa: BLE001
        log.exception("learn_from_turn failed")


def _admin_id() -> int:
    from app.config import settings
    return settings.admin_telegram_id
