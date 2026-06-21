"""FastAPI application entrypoint — backend API + runs the Telegram bot.

There is NO web admin panel: all administration happens inside Telegram for the
admin user (ADMIN_TELEGRAM_ID). FastAPI here only provides health/stats JSON
endpoints and hosts the bot's polling loop so a single `docker compose up -d`
brings everything online.
"""
from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.routes import router as api_router
from app.bot.admin_handlers import router as bot_admin_router
from app.bot.bot import bot, dp
from app.bot.group_handlers import router as bot_group_router
from app.bot.handlers import router as bot_router
from app.database import ping
from app.logger import get_logger, setup_logging
from app.migrate import run_upgrade
from app.services import vector_service

setup_logging()
log = get_logger("app")

# Register bot routers. Order matters:
#   1) group router — consumes group/supergroup messages (logging only)
#   2) admin router — admin-only DM commands
#   3) main router  — everything else in DMs
dp.include_router(bot_group_router)
dp.include_router(bot_admin_router)
dp.include_router(bot_router)


async def _wait_for_db(retries: int = 30, delay: float = 2.0) -> None:
    last = None
    for attempt in range(1, retries + 1):
        try:
            await ping()
            log.info("Database reachable.")
            return
        except Exception as e:  # noqa: BLE001
            last = e
            log.warning("DB not ready (attempt %s/%s): %s", attempt, retries, e)
            await asyncio.sleep(delay)
    raise RuntimeError(f"Database never became ready: {last}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _wait_for_db()
    await asyncio.to_thread(run_upgrade)  # apply Alembic migrations to head
    await vector_service.init()           # ensure Qdrant collection (best-effort)

    me = await bot.get_me()
    log.info("Starting bot @%s (v%s) …", me.username, __version__)
    await bot.delete_webhook(drop_pending_updates=True)
    polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))

    try:
        yield
    finally:
        log.info("Shutting down bot…")
        polling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await polling_task
        await bot.session.close()
        await vector_service.close()


app = FastAPI(title="AI Telegram Bot", version=__version__, lifespan=lifespan)

app.include_router(api_router)


@app.get("/")
async def root():
    return {
        "service": "ai-telegram-bot",
        "version": __version__,
        "status": "running",
        "admin": "in-telegram only",
    }
