# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow Rules

- **NO CODE CHANGES WITHOUT APPROVAL** — Discuss proposed changes, rationale, and impact before implementing.
- **All development in `development` branch** — `main` is production-only and must always be deployable.
- Merge to `main` only when code is fully tested and stable. Tag releases in `main`.

## Running the Bot

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot (requires .env with DISCORD_TOKEN)
python main.py

# Debug logging
LOG_LEVEL=DEBUG python main.py
```

There are no automated tests. Validation is done by running the bot and exercising commands in Discord.

## Environment Setup

Create a `.env` file (see `README_ENV.md` for all variables). Minimum required:

```bash
DISCORD_TOKEN=your_discord_bot_token
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-chat
```

Priority order: shell env vars > `.env` file > `config.py` defaults.

## Architecture

### Message Flow

1. `main.py` — loads `.env`, calls `create_bot()`, runs with `DISCORD_TOKEN`
2. `bot.py` — Discord event hub; `on_message` routes to response pipeline or command processing
3. On first message in a channel, `load_channel_history()` backfills in-memory `channel_history`
4. For addressed messages (bot prefix or provider override), calls `build_context_for_provider()` then `handle_ai_response()`
5. All messages also captured in real-time to SQLite via `raw_events.py` listeners (independent of response pipeline)

### Two Parallel History Systems

The codebase maintains **two separate, independent history systems**:

| System | Location | Purpose |
|--------|----------|---------|
| **In-memory** (`channel_history`) | `utils/history/` | AI conversation context; used for API calls |
| **SQLite persistence** | `utils/message_store.py` + `utils/raw_events.py` | Durable storage for all messages; foundation for future summarization (v3.1.0) |

These do not share code. Changes to one do not affect the other.

### Context Pipeline (In-Memory)

`channel_history[channel_id]` → `prepare_messages_for_api()` (noise filter) → `build_context_for_provider()` (token budget trim) → AI provider API call

Token budget formula: `input_budget = (context_window × CONTEXT_BUDGET_PERCENT / 100) − max_output_tokens`

### Provider System

- `ai_providers/__init__.py` — `get_provider()` factory with singleton cache (one instance per provider type for the bot's lifetime)
- Each provider (`openai_provider.py`, `anthropic_provider.py`, `openai_compatible_provider.py`) extends `base.py`
- **All synchronous API calls must be wrapped in `asyncio.to_thread()` or `run_in_executor()`** to prevent Discord heartbeat blocking
- Provider selection order: explicit override (e.g., `openai, tell me...`) → channel setting → `AI_PROVIDER` env var

### Settings Persistence

Bot settings (system prompt, AI provider, auto-respond, thinking mode) are **parsed from Discord message history** on channel load via `utils/history/realtime_settings_parser.py`. There is no settings database — settings are recovered by replaying `!command` messages found in history.

### Key Shared State (in `utils/history/storage.py`)

- `channel_history` — `defaultdict(list)` of message dicts per channel ID
- `loaded_history_channels` — tracks which channels have had history loaded
- `channel_locks` — per-channel async locks to prevent concurrent loads

## Code Quality Standards

- **250-line file limit** — mandatory for all files; split into focused modules if exceeded
- **Single responsibility** — each module has one clear purpose
- **Async safety** — never block the Discord event loop; wrap all synchronous I/O in `asyncio.to_thread()`
- **Version tracking** — every file has a version header and changelog in its docstring
- Each new file must include module-level logging via `get_logger('module_name')` from `utils/logging_utils.py`

## Verifying the SQLite Database

```bash
python3 -c "from utils.message_store import init_database, _get_conn; init_database(); print(_get_conn().execute('SELECT COUNT(*) FROM messages').fetchone()[0])"
```

Delete `data/messages.db` to reset; messages will be re-backfilled on restart (up to 10,000 per channel).
