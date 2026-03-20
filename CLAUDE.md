# CLAUDE.md
# Version 2.0.0

This file provides guidance to Claude Code when working with this repository.

## Workflow Rules

- **NO CODE CHANGES WITHOUT APPROVAL** — discuss first, wait for approval
- **Always present complete files** — never partial diffs or patches
- **Increment version numbers** — bump header and update docstring changelog
- **Update STATUS.md and HANDOFF.md** alongside every code change
- **All development in `development` or feature branches** — `main` is production

## Running the Bot

```bash
pip install -r requirements.txt
python main.py                    # requires .env with DISCORD_TOKEN
LOG_LEVEL=DEBUG python main.py    # debug logging
```

No automated tests. Validation via Discord commands.

## Environment Setup

```bash
# Required
DISCORD_TOKEN=your_discord_bot_token
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-chat

# Summarization
SUMMARIZER_PROVIDER=gemini
SUMMARIZER_MODEL=gemini-3.1-flash-lite-preview
SUMMARIZER_BATCH_SIZE=500
GEMINI_API_KEY=your_gemini_key
GEMINI_MAX_TOKENS=32768

# Optional
DATABASE_PATH=./data/messages.db
CONTEXT_BUDGET_PERCENT=80
```

Priority: shell env vars > `.env` file > `config.py` defaults.

## Architecture

### Message Flow
1. `main.py` → loads .env, creates bot, runs with DISCORD_TOKEN
2. `bot.py` → on_message routes to response pipeline or commands
3. First message in channel triggers `load_channel_history()` backfill
4. Addressed messages → `build_context_for_provider()` → `handle_ai_response()`
5. `raw_events.py` → persists every message to SQLite in parallel

### Summarization Pipeline (v3.3.0+)
Cold start (all messages, no prior summary):
```
Raw messages → Secretary (natural language minutes, no JSON)
            → Structurer (JSON delta ops via Gemini Structured Outputs)
            → apply_ops() → verify hashes → save
```

Incremental update (new messages since last summary):
```
New messages + CURRENT_STATE snapshot → Gemini Structured Outputs
            → delta ops JSON → apply_ops() → verify → save
```

Key files: `summarizer.py` (router), `summarizer_authoring.py` (cold start),
`summary_prompts.py` (incremental prompt), `summary_prompts_authoring.py`
(Secretary/Structurer prompts), `summary_schema.py` (ops, hashes, verification)

### Noise Filtering
All bot output prefixed with ℹ️ (noise) or ⚙️ (settings persistence).
Filters in `message_processing.py`: `is_noise_message()`, `is_settings_message()`,
`is_admin_output()`. Legacy patterns retained for pre-prefix messages.

### Providers
- OpenAI, Anthropic, DeepSeek (conversation) — per-channel configurable
- Gemini (summarization only) — not used for conversation
- All providers: singleton cached, async executor wrapped

### Persistence
- SQLite with WAL mode (`data/messages.db`)
- `raw_events.py` captures all messages including bot responses
- `db_migration.py` applies `schema/NNN.sql` files sequentially
- Settings recovered from Discord history on startup

## Key Design Decisions

- **Decision = agreement on action** — "I think X" / "Agreed" → decision.
  "What is X?" / "X is Y" → fact, NOT a decision.
- **Fresh-from-source > recursive** — Gemini's 1M context sends raw messages
  directly, eliminating recursive summary drift
- **Secretary writes freely** — no JSON constraint in Pass 1
- **Prefix-based filtering** — single ℹ️/⚙️ check replaces 30+ patterns
- **Hash protection** — SHA-256 on protected fields, supersession lifecycle

## Commands Reference

| Command | Description |
|---------|-------------|
| `!summary` | Show channel summary |
| `!summary full/raw` | Full view / Secretary's raw minutes |
| `!summary create/clear` | Run summarization / delete (admin) |
| `!debug noise/cleanup/status` | Maintenance tools (admin) |
| `!status` | Bot settings for this channel |
| `!autorespond` | Auto-response toggle |
| `!ai` | AI provider switch |
| `!thinking` | DeepSeek thinking display |
| `!prompt` | System prompt management |
| `!history` | View/clean/reload history |

## Code Conventions

- 250-line file limit — extract to new module when exceeded
- All `ctx.send()` must use ℹ️ or ⚙️ prefix
- Version header + docstring changelog in every file
- `asyncio.to_thread()` for all SQLite operations
- `run_in_executor()` for all provider API calls
