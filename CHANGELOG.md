# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-06-21

### Added
- **Conversations** — messages are now grouped into conversations (like the
  ChatGPT app). Every message carries a `conversation_id`.
- **📜 History** menu — browse previous conversations, each with an
  auto-generated short recap title, and tap to resume one (context restored).
- **Qdrant vector engine** for per-user personalization. User messages are
  embedded (`text-embedding-3-small`) and stored per user; relevant memories are
  recalled at chat time and injected into the prompt. Added as a service in
  `docker-compose` (REST on host `:6339`). Fully best-effort — the bot keeps
  working if Qdrant is down.
- **User segmentation tags / badges** (`user_tags` table). Admin commands
  `/tag`, `/untag`, `/classify` (LLM auto-classification into a controlled
  vocabulary). Tags are auto-suggested every 8 user messages and shown on the
  admin user card.
- **`user_memories`** table — relational mirror of what is stored in the vector
  engine.
- **Application versioning** — `__version__`, `GET /api/version`, version shown
  in startup logs and the FastAPI app; this `CHANGELOG.md`.
- Alembic migration `0002` (additive, backfills existing messages into an
  "Imported chat" conversation — safe to run on a live production database).

### Changed
- **New chat** no longer deletes messages. It archives the current conversation
  (saving a recap to History) and opens a fresh one; it still resets the model
  to the default.
- Chat context is now scoped to the active conversation.

## [0.2.0] - 2026-06-21

### Added
- **Alembic** migrations with version-by-version development; `alembic upgrade
  head` runs automatically on startup.
- `migrations` table logging every applied revision (timestamp + direction),
  alongside Alembic's own `alembic_version`.
- `model_selections` log table (current model = latest row).
- `token_audits` fact table for durable per-message token accounting.

### Changed
- `users` is now a pure **dimension** table — running totals and the selected
  model moved out into dedicated log/fact tables.

### Removed
- `Base.metadata.create_all` startup path (replaced by migrations).
- `selected_model`, `message_count`, `total_tokens`, `prompt_tokens`,
  `completion_tokens`, `image_count` columns from `users`.

## [0.1.2] - 2026-06-20

### Added
- **Image editing** — send a photo with a prompt and choose 🎨 Transform/Edit to
  redraw it (via `gpt-image-1`), or 👁 Describe.

### Changed
- **New chat** now also resets the selected model back to the default.

## [0.1.1] - 2026-06-20

### Fixed
- Telegram message formatting: model Markdown (`**bold**`, headings, code, links)
  is converted to Telegram-safe HTML instead of showing literal `*`.
- Image generation falls back across `gpt-image-1` → `dall-e-3` → `dall-e-2` and
  handles both URL and base64 responses (fixes "model 'dall-e-3' does not exist").

## [0.1.0] - 2026-06-20

### Added
- Initial professional AI Telegram chatbot: multi-model OpenAI chat, DALL·E
  image generation, vision, Whisper voice, personas, glass keyboards.
- FastAPI backend + PostgreSQL storage of users and messages.
- In-chat admin panel (stats, broadcast, user lookup, ban/unban) for the admin
  Telegram ID.
- Dockerised: `docker compose up -d` (app `:8009`, db `:5439`).

[Unreleased]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/releases/tag/v0.3.0
[0.2.0]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/releases/tag/v0.2.0
[0.1.2]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/releases/tag/v0.1.2
[0.1.1]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/releases/tag/v0.1.1
[0.1.0]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/releases/tag/v0.1.0
