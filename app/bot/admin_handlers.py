"""Admin-only handlers inside the bot (extra access for ADMIN_TELEGRAM_ID)."""
from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message as TgMessage

from app.bot import keyboards as kb
from app.bot.bot import bot
from app.bot.states import AdminStates
from app.config import settings
from app.database import SessionLocal
from app.services import crud

log = logging.getLogger(__name__)
router = Router()


def is_admin(uid: int) -> bool:
    return uid == settings.admin_telegram_id


# Guard: all handlers in this router require admin
router.message.filter(F.from_user.id == settings.admin_telegram_id)
router.callback_query.filter(F.from_user.id == settings.admin_telegram_id)


@router.message(Command("admin"))
@router.message(F.text == kb.BTN_ADMIN)
async def admin_panel(message: TgMessage):
    await message.answer(
        "🛠 <b>Admin panel</b>\nManage your bot from here, or open the full web dashboard.",
        reply_markup=kb.admin_kb(),
    )


async def _stats_text() -> str:
    async with SessionLocal() as session:
        s = await crud.get_stats(session)
    return (
        "📊 <b>Bot statistics</b>\n\n"
        f"👥 Total users: <b>{s['total_users']}</b>\n"
        f"🟢 Active (24h): <b>{s['active_24h']}</b>\n"
        f"🆕 New (24h): <b>{s['new_24h']}</b>\n"
        f"📈 New (7d): <b>{s['new_7d']}</b>\n"
        f"🚫 Banned: <b>{s['banned_users']}</b>\n"
        f"💬 Messages: <b>{s['total_messages']}</b>\n"
        f"🎨 Images: <b>{s['total_images']}</b>\n"
        f"🔢 Tokens: <b>{s['total_tokens']:,}</b>"
    )


@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(call: CallbackQuery):
    await call.answer()
    await call.message.answer(await _stats_text())


@router.callback_query(F.data == "admin:users")
async def cb_admin_users(call: CallbackQuery):
    await call.answer()
    async with SessionLocal() as session:
        users = await crud.list_users(session, limit=15)
    lines = ["👥 <b>Recent users</b>\n"]
    for u in users:
        uname = f"@{u.username}" if u.username else "—"
        flag = "🚫" if u.is_banned else ("👑" if u.is_admin else "👤")
        lines.append(f"{flag} <code>{u.telegram_id}</code> {uname} · {u.full_name}")
    lines.append("\n<i>Inspect anyone with /user &lt;id&gt; or /find &lt;username&gt;</i>")
    await call.message.answer("\n".join(lines))


@router.callback_query(F.data == "admin:top")
async def cb_admin_top(call: CallbackQuery):
    await call.answer()
    async with SessionLocal() as session:
        rows = await crud.list_top_users(session, limit=10)
    lines = ["🏆 <b>Top users by activity</b>\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, (u, msgs, tokens) in enumerate(rows):
        rank = medals[i] if i < 3 else f"{i + 1}."
        uname = f"@{u.username}" if u.username else u.full_name
        lines.append(f"{rank} {uname} — {msgs} msgs · {tokens:,} tok")
    await call.message.answer("\n".join(lines))


@router.callback_query(F.data == "admin:broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(AdminStates.waiting_broadcast)
    await call.message.answer(
        "📢 <b>Broadcast</b>\nSend me the message (text/HTML) to deliver to every user.\n"
        "Send /cancel to abort."
    )


@router.message(Command("cancel"))
async def cancel(message: TgMessage, state: FSMContext):
    await state.clear()
    await message.answer("❌ Cancelled.", reply_markup=kb.main_menu(True))


@router.message(AdminStates.waiting_broadcast, F.text)
async def do_broadcast(message: TgMessage, state: FSMContext):
    await state.clear()
    text = message.html_text
    async with SessionLocal() as session:
        ids = await crud.all_user_ids(session)

    await message.answer(f"📤 Sending to {len(ids)} users…")
    sent = failed = 0
    for uid in ids:
        try:
            await bot.send_message(uid, text)
            sent += 1
        except Exception:  # noqa: BLE001
            failed += 1
        await asyncio.sleep(0.05)  # respect Telegram rate limits

    async with SessionLocal() as session:
        await crud.log_broadcast(session, text, sent, failed)
    await message.answer(
        f"✅ <b>Broadcast complete</b>\nDelivered: {sent}\nFailed: {failed}",
        reply_markup=kb.main_menu(True),
    )


# ---- Quick text commands: /ban <id>, /unban <id>, /user <id> ----

@router.message(Command("ban"))
async def cmd_ban(message: TgMessage):
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        return await message.answer("Usage: <code>/ban &lt;telegram_id&gt;</code>")
    async with SessionLocal() as session:
        ok = await crud.set_banned(session, int(parts[1]), True)
    await message.answer("✅ Banned." if ok else "User not found.")


@router.message(Command("unban"))
async def cmd_unban(message: TgMessage):
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        return await message.answer("Usage: <code>/unban &lt;telegram_id&gt;</code>")
    async with SessionLocal() as session:
        ok = await crud.set_banned(session, int(parts[1]), False)
    await message.answer("✅ Unbanned." if ok else "User not found.")


async def _user_card(session, u) -> str:
    model = await crud.get_current_model(session, u)
    usage = await crud.user_usage(session, u.id)
    return (
        f"👤 <b>{u.full_name}</b>\n"
        f"ID: <code>{u.telegram_id}</code>\n"
        f"Username: @{u.username or '—'}\n"
        f"Phone: {u.phone_number or '—'}\n"
        f"Lang: {u.language_code or '—'} · Premium: {u.is_premium}\n"
        f"Model: {model}\n"
        f"Messages: {usage['messages']} · Images: {usage['images']}\n"
        f"Tokens: {usage['total_tokens']:,} "
        f"(in {usage['prompt_tokens']:,} / out {usage['completion_tokens']:,})\n"
        f"Banned: {u.is_banned} · Admin: {u.is_admin}\n"
        f"Joined: {u.created_at:%Y-%m-%d %H:%M} · Last seen: {u.last_active:%Y-%m-%d %H:%M}"
    )


@router.message(Command("user"))
async def cmd_user(message: TgMessage):
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        return await message.answer("Usage: <code>/user &lt;telegram_id&gt;</code>")
    async with SessionLocal() as session:
        u = await crud.get_user_by_telegram_id(session, int(parts[1]))
        if not u:
            return await message.answer("User not found.")
        card = await _user_card(session, u)
    await message.answer(card, reply_markup=kb.admin_user_kb(u.telegram_id, u.is_banned))


@router.message(Command("find"))
async def cmd_find(message: TgMessage):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        return await message.answer("Usage: <code>/find &lt;username&gt;</code>")
    async with SessionLocal() as session:
        u = await crud.find_user_by_username(session, parts[1].strip())
        if not u:
            return await message.answer("No user with that username.")
        card = await _user_card(session, u)
    await message.answer(card, reply_markup=kb.admin_user_kb(u.telegram_id, u.is_banned))


@router.callback_query(F.data.startswith("adm_ban:"))
async def cb_ban(call: CallbackQuery):
    tid = int(call.data.split(":", 1)[1])
    async with SessionLocal() as session:
        await crud.set_banned(session, tid, True)
        u = await crud.get_user_by_telegram_id(session, tid)
        card = await _user_card(session, u) if u else None
    await call.answer("Banned ✅")
    if u:
        await call.message.edit_text(card, reply_markup=kb.admin_user_kb(tid, True))


@router.callback_query(F.data.startswith("adm_unban:"))
async def cb_unban(call: CallbackQuery):
    tid = int(call.data.split(":", 1)[1])
    async with SessionLocal() as session:
        await crud.set_banned(session, tid, False)
        u = await crud.get_user_by_telegram_id(session, tid)
        card = await _user_card(session, u) if u else None
    await call.answer("Unbanned ✅")
    if u:
        await call.message.edit_text(card, reply_markup=kb.admin_user_kb(tid, False))
