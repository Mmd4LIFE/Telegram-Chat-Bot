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


def _split(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split text into <=limit chunks, preferring newline boundaries."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:  # a single very long line
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit:
            parts.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        parts.append(current)
    return parts


async def send_long(chat_id: int, text: str, **kwargs):
    """Send a (possibly long) message, splitting on Telegram's 4096-char limit."""
    if not text:
        text = "🤔 (empty response)"
    for chunk in _split(text):
        await bot.send_message(chat_id, chunk, **kwargs)
        kwargs.pop("reply_markup", None)  # only first chunk carries the keyboard
