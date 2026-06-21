# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.1] - 2026-06-21

### Added
- `users.is_active` flag. Group members are now **force-created as non-active
  users** the first moment they're seen in a group, so each has an internal id
  immediately (emoji stats + vector memory work right away). They're promoted to
  active the moment they DM the bot (migration `0006`).
- Group messages also store the **raw Telegram identity** (`telegram_user_id`,
  `username`, `first_name`) so no message is ever lost regardless of user state
  (migration `0005`).
- Admin stats now show "started / known" user counts; user card shows
  `Started bot`.

### Changed
- Broadcasts only target **active** users (the bot cannot message people who
  never started it).

## [0.5.0] - 2026-06-21

### Added
- **Group logger** — when added to a group (with privacy mode disabled in
  BotFather), the bot captures every message of every type and stores it in new
  `groups` / `group_messages` tables. Voice & round-video notes are transcribed
  with Whisper; stickers store their emoji + `file_id`; photos/videos/etc. are
  logged with type and caption.
- **Emoji-aware personalization** — `user_emoji_stats` tracks each user's most
  used emojis (from both DMs and groups); the bot is told a user's favourite
  emojis and naturally mirrors them in replies.
- Group text and transcribed voice feed the same per-user vector memory, so
  personalization spans DMs *and* groups.
- Group statistics in the admin 📊 panel.
- Centralized logging module (`app/logger.py`).
- Migration `0004` (groups, group_messages, user_emoji_stats).

### Changed
- **Models reorganised into a package** (`app/models/`), one module per related
  group of tables (user, conversation, message, model_selection, token_audit,
  group, system).

## [0.4.0] - 2026-06-21

### Changed
- **Segmentation tagging is now computed at the END of each conversation**
  (instead of every 8 messages), based on that conversation's transcript. The
  user's current primary tag is stored on `users.segment`.
- **User notifications about their tag** follow new rules: only users with **more
  than 10 used conversations** are ever told their tag; they are told once when
  they qualify, and afterwards only when the tag **changes** — never on every
  conversation. The last notified value is tracked in `users.segment_notified`.

### Added
- `users.segment` and `users.segment_notified` columns (migration `0003`).
- Human-friendly tag labels and a single-best `classify_primary_tag`.

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

[Unreleased]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/releases/tag/v0.5.1
[0.5.0]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/releases/tag/v0.5.0
[0.4.0]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/releases/tag/v0.4.0
[0.3.0]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/releases/tag/v0.3.0
[0.2.0]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/releases/tag/v0.2.0
[0.1.2]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/releases/tag/v0.1.2
[0.1.1]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/releases/tag/v0.1.1
[0.1.0]: https://github.com/Mmd4LIFE/Telegram-Chat-Bot/releases/tag/v0.1.0
