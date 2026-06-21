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
- 🧠 Conversation memory (last N messages) with `🆕 New chat` to start fresh
- 📜 **Conversation history** — past chats are saved with an auto-generated recap
  title; browse and resume them like the ChatGPT app
- ✨ **Personalization** — a Qdrant vector engine remembers each user across
  chats and tailors replies ("personalization is all you need")
- 📊 Personal usage stats
- Glassy UX: persistent `ReplyKeyboardMarkup` menu + inline "glass" keyboards

**For the admin (Telegram ID `592354162`)** — everything is in the chat:
- `🛠 Admin` button → stats, recent users, top users, broadcast
- 📢 Broadcast to all users (with rate-limit-safe sending)
- 👤 Inspect any user: `/user <id>` or `/find <username>` (full profile card incl. tags)
- 🚫 Ban / unban inline or via `/ban <id>` `/unban <id>`
- 🏷 Segmentation tags / badges: `/tag <id> <tag>`, `/untag <id> <tag>`,
  `/classify <id>` (LLM auto-classifies the user). The bot also recomputes a
  primary tag at the **end of each conversation**; users with **>10
  conversations** are told their tag once, then only when it **changes**.

**Data** — a small **star schema** in PostgreSQL, managed by **Alembic**
migrations (version-by-version):

| Table | Role | Holds |
|---|---|---|
| `users` | **dimension** | Telegram profile, language, premium, phone, admin/ban flags, persona — *descriptive attributes only, no measures* |
| `conversations` | content | chat sessions with recap title; one is active per user |
| `messages` | content | conversation messages, each with a `conversation_id` |
| `model_selections` | **log** | one row per model change — the *current* model is the latest row |
| `token_audits` | **fact** | per-message token accounting (prompt/completion/total) — durable, survives chat resets |
| `user_tags` | **log** | segmentation badges per user (admin/auto) |
| `user_memories` | log | relational mirror of vectors stored in Qdrant |
| `broadcast_logs` | log | admin broadcast history |
| `alembic_version` | — | Alembic's current head |
| `migrations` | **log** | every migration applied, with timestamp + direction |

Plus **Qdrant** (separate service, host `:6339`) holding per-user message
embeddings for personalization.

### Migrations

Migrations run automatically on startup (`alembic upgrade head` inside the app
lifespan), so `docker compose up -d` always brings the DB to the latest version.
Every applied revision is also recorded in the `migrations` table.

Create a new version after changing models:

```bash
docker compose exec app alembic revision --autogenerate -m "describe change"
# review the generated file in alembic/versions/, then it applies on next start
docker compose exec app alembic upgrade head     # or just restart
docker compose exec app alembic history          # see all versions
docker compose exec app alembic downgrade -1     # roll back one version
```

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
├── db      → postgres:16   (host :5439)
├── qdrant  → qdrant:1.12   (host :6339)  per-user personalization vectors
└── app     → FastAPI (host :8009)
              ├── /api/*          JSON backend (health, stats, version)
              └── aiogram bot     long-polling, started in FastAPI lifespan
                                  (runs Alembic migrations + Qdrant init first)
```

Single container runs both the API and the bot, so one `up -d` is all you need.
