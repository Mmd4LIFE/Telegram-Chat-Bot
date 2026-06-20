"""Bot & Dispatcher singletons plus small helpers."""
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings

bot = Bot(
    token=settings.telegram_bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())

TELEGRAM_LIMIT = 4096


async def send_long(chat_id: int, text: str, **kwargs):
    """Send a message, splitting on Telegram's 4096-char limit."""
    if not text:
        text = "🤔 (empty response)"
    for i in range(0, len(text), TELEGRAM_LIMIT):
        await bot.send_message(chat_id, text[i : i + TELEGRAM_LIMIT], **kwargs)
        kwargs.pop("reply_markup", None)  # only first chunk carries the keyboard
