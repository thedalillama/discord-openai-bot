# CLAUDE.md
# Version 1.2.0

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow Rules

- **NO CODE CHANGES WITHOUT APPROVAL** — Discuss proposed changes, rationale, and impact before implementing. Wait for explicit approval before writing any code.
- **Always present complete files** — Never show partial diffs or snippets when delivering code changes. Always present the full file contents.
- **Increment version numbers before committing** — Every file has a version header (e.g., `# Version 1.2.0`). Bump the version in the file header as part of the change, and update the changelog block in the docstring.
- **Update STATUS.md and HANDOFF.md alongside code changes** — Any version bump must be reflected in STATUS.md (version history) and HANDOFF.md (current state). These are not optional.
- **All development in `development` branch** — `main` is production-only and must always be deployable. Merge only when fully tested and stable. Tag releases in `main`.

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

Optional but notable: `DATABASE_PATH` (default `./data/messages.db`) — override to store the SQLite database at a different location. The `data/` directory is created automatically.

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
| **SQLite persistence** | `utils/message_store.py` + `utils/raw_events.py` | Durable storage for all messages; foundation for future summarization |

These do not share code. Changes to one do not affect the other.

### Context Pipeline (In-Memory)

`channel_history[channel_id]` → `prepare_messages_for_api()` (noise filter) → `build_context_for_provider()` (token budget trim) → AI provider API call

Token budget formula: `input_budget = (context_window × CONTEXT_BUDGET_PERCENT / 100) − max_output_tokens`

### Provider System

- `ai_providers/__init__.py` — `get_provider()` factory with singleton cache (one instance per provider type for the bot's lifetime)
- Each provider (`openai_provider.py`, `anthropic_provider.py`, `openai_compatible_provider.py`) extends `base.py`
- **All synchronous provider API calls must use `loop.run_in_executor()` with `ThreadPoolExecutor`** — this is the established pattern across all three providers. Do not use `asyncio.to_thread()` for provider calls; it will break the established convention and risks heartbeat blocking.

```python
import asyncio
import concurrent.futures

loop = asyncio.get_event_loop()
with concurrent.futures.ThreadPoolExecutor() as executor:
    result = await loop.run_in_executor(
        executor,
        lambda: synchronous_api_call(params)
    )
```

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
- **Async safety** — never block the Discord event loop. Two patterns are in use; use the right one for the context:
  - `loop.run_in_executor()` with `ThreadPoolExecutor` — for AI provider API calls (all three providers)
  - `asyncio.to_thread()` — for SQLite writes in `utils/raw_events.py`
- **Version tracking** — every file has a version header and changelog in its docstring; bump both on every change
- Each new file must include module-level logging via `get_logger('module_name')` from `utils/logging_utils.py`

## Known Pitfalls

### bot.add_listener() vs @bot.event for on_message

`commands.Bot` does **not** dispatch `on_raw_message_create` when `@bot.event on_message` is defined. The v3.0.0 persistence layer hit this bug — the fix was registering the SQLite capture handler as a second `on_message` listener via `bot.add_listener()`, which coexists with the primary `@bot.event` handler in `bot.py`.

**Do not:**
- Replace the `bot.add_listener(persistence_on_message, 'on_message')` call in `raw_events.py` with `@bot.event`
- Switch the persistence capture to `on_raw_message_create`

Both will silently break message capture. The `@bot.event` decorator sets the **primary** handler (only one allowed); `bot.add_listener()` registers **additional** listeners that fire alongside it.

## SOW Convention

Every version has a Statement of Work document in `docs/sow/` (e.g., `SOW_v3.0.0.md`). When implementing a new version, create the corresponding SOW before writing code. SOW documents define the problem statement, objective, and implementation plan for that version.

## Verifying the SQLite Database

```bash
python3 -c "
from utils.message_store import init_database, get_database_stats
init_database()
stats = get_database_stats()
print(stats)
"
```

Delete `data/messages.db` to reset; messages will be re-backfilled on restart (up to 10,000 per channel).
