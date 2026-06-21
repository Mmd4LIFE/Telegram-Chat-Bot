"""Keyboards — persistent reply menu + inline ("glass") buttons."""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.services.openai_service import CHAT_MODELS, IMAGE_MODEL

# ───── Buttons (labels) used in the persistent reply keyboard ─────
BTN_NEW_CHAT = "🆕 New chat"
BTN_HISTORY = "📜 History"
BTN_MODELS = "🤖 Models"
BTN_IMAGE = "🎨 Image"
BTN_PERSONA = "🎭 Persona"
BTN_STATS = "📊 My stats"
BTN_HELP = "ℹ️ Help"
BTN_ADMIN = "🛠 Admin"


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text=BTN_NEW_CHAT), KeyboardButton(text=BTN_HISTORY))
    kb.row(KeyboardButton(text=BTN_MODELS), KeyboardButton(text=BTN_IMAGE))
    kb.row(KeyboardButton(text=BTN_PERSONA), KeyboardButton(text=BTN_STATS))
    kb.row(KeyboardButton(text=BTN_HELP))
    if is_admin:
        kb.row(KeyboardButton(text=BTN_ADMIN))
    return kb.as_markup(resize_keyboard=True, input_field_placeholder="Ask me anything…")


def conversations_kb(items) -> InlineKeyboardMarkup:
    """`items` is a list of (Conversation, message_count). Glass list of past chats."""
    kb = InlineKeyboardBuilder()
    for conv, count in items:
        title = conv.title or "Untitled chat"
        active = "🟢 " if conv.is_active else ""
        label = f"{active}{title} · {count} msgs"
        kb.row(InlineKeyboardButton(text=label[:60], callback_data=f"conv:{conv.id}"))
    kb.row(InlineKeyboardButton(text="🆕 Start new chat", callback_data="conv:new"))
    return kb.as_markup()


def share_contact_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="📱 Share my phone", request_contact=True))
    kb.row(KeyboardButton(text="⏭ Skip"))
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)


def models_kb(current: str) -> InlineKeyboardMarkup:
    """Glass inline keyboard for picking a chat model."""
    kb = InlineKeyboardBuilder()
    for m in CHAT_MODELS:
        mark = "✅ " if m.id == current else ""
        kb.row(InlineKeyboardButton(text=f"{mark}{m.label}", callback_data=f"model:{m.id}"))
    kb.row(InlineKeyboardButton(text="🎨 DALL·E 3 (images)", callback_data=f"model:{IMAGE_MODEL}"))
    return kb.as_markup()


def photo_action_kb() -> InlineKeyboardMarkup:
    """Choice shown when a user sends a photo with a caption."""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🎨 Transform / Edit", callback_data="img:edit"))
    kb.row(InlineKeyboardButton(text="👁 Describe it", callback_data="img:describe"))
    return kb.as_markup()


def persona_kb() -> InlineKeyboardMarkup:
    personas = [
        ("🤖 Default assistant", ""),
        ("👨‍💻 Senior developer", "You are a senior software engineer. Give precise, expert, code-first answers."),
        ("✍️ Creative writer", "You are an award-winning creative writer with a vivid, engaging style."),
        ("🎓 Patient teacher", "You are a patient teacher who explains step by step with simple examples."),
        ("💼 Business consultant", "You are a sharp business strategist. Be concise, structured and actionable."),
        ("🌐 Translator", "You are a professional translator. Detect the language and translate accurately."),
    ]
    kb = InlineKeyboardBuilder()
    for label, prompt in personas:
        # encode index instead of long prompt
        kb.row(InlineKeyboardButton(text=label, callback_data=f"persona:{personas.index((label, prompt))}"))
    return kb.as_markup()


PERSONAS = [
    "",
    "You are a senior software engineer. Give precise, expert, code-first answers.",
    "You are an award-winning creative writer with a vivid, engaging style.",
    "You are a patient teacher who explains step by step with simple examples.",
    "You are a sharp business strategist. Be concise, structured and actionable.",
    "You are a professional translator. Detect the language and translate accurately.",
]


def admin_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📊 Statistics", callback_data="admin:stats"))
    kb.row(
        InlineKeyboardButton(text="👥 Recent users", callback_data="admin:users"),
        InlineKeyboardButton(text="🏆 Top users", callback_data="admin:top"),
    )
    kb.row(InlineKeyboardButton(text="📢 Broadcast", callback_data="admin:broadcast"))
    kb.row(InlineKeyboardButton(text="🔄 Refresh", callback_data="admin:stats"))
    return kb.as_markup()


def admin_user_kb(telegram_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if is_banned:
        kb.row(InlineKeyboardButton(text="✅ Unban", callback_data=f"adm_unban:{telegram_id}"))
    else:
        kb.row(InlineKeyboardButton(text="🚫 Ban", callback_data=f"adm_ban:{telegram_id}"))
    return kb.as_markup()
