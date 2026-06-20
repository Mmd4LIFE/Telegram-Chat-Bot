# 🤖 Professional AI Telegram Chatbot

A production-ready Telegram chatbot powered by OpenAI — a drop-in replacement for
ChatGPT inside Telegram. FastAPI backend, PostgreSQL storage of **everything**,
and a full **in-chat admin panel** for the owner.

## ✨ Features

**For everyone**
- 💬 Chat with multiple OpenAI models — GPT-4o, GPT-4.1, GPT-4 Turbo, o1/o3-mini, GPT-3.5
- 🎨 Image generation from text (`🎨 Image` mode)
- 🪄 Image **editing / transformation** — send a photo + a prompt (e.g. the viral
  "draw me as a chaotic fan-art sketchbook page") and pick 🎨 Transform
- 🖼 Vision — send a photo and the bot analyses it
- 🎙 Voice — send a voice message, it's transcribed with Whisper and answered
- 🎭 Personas — turn the assistant into a developer, teacher, writer, translator…
- 🧠 Conversation memory (last N messages) with `🆕 New chat` to reset
- 📊 Personal usage stats
- Glassy UX: persistent `ReplyKeyboardMarkup` menu + inline "glass" keyboards

**For the admin (Telegram ID `592354162`)** — everything is in the chat:
- `🛠 Admin` button → stats, recent users, top users, broadcast
- 📢 Broadcast to all users (with rate-limit-safe sending)
- 👤 Inspect any user: `/user <id>` or `/find <username>` (full profile card)
- 🚫 Ban / unban inline or via `/ban <id>` `/unban <id>`

**Data** — every user and every message is stored in PostgreSQL
(`users` + `messages` tables): Telegram profile, language, premium flag, phone
(if shared), selected model, token usage, image count, timestamps, and more.

## 🚀 Run it

Everything is already configured in `.env`. Just:

```bash
docker compose up -d
```

- Bot starts polling automatically — open Telegram and message it.
- Backend API: http://localhost:8009  (`/api/health`, `/api/stats`)
- PostgreSQL exposed on host port **5439**.

Check logs:

```bash
docker compose logs -f app
```

Stop:

```bash
docker compose down          # keep data
docker compose down -v       # wipe the database too
```

## 🔧 Configuration (`.env`)

| Variable | Meaning |
|---|---|
| `OPENAI_API_KEY` | OpenAI key |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `ADMIN_TELEGRAM_ID` | Telegram ID with admin powers |
| `DEFAULT_MODEL` | Model new users start on |
| `CONTEXT_MESSAGES` | How many past messages to send as context |
| `APP_PORT` / db ports | Fixed to 8009 / 5439 in compose |

> ⚠️ The committed `.env` contains live API keys you provided. Keep this repo
> private and rotate the keys if they were ever exposed.

## 🏗 Architecture

```
docker compose
├── db    → postgres:16  (host :5439)
└── app   → FastAPI (host :8009)
            ├── /api/*          JSON backend (health, stats)
            └── aiogram bot     long-polling, started in FastAPI lifespan
```

Single container runs both the API and the bot, so one `up -d` is all you need.
