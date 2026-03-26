# CLAUDE.md
# Version 4.0.0

This file provides guidance to Claude Code when working with this repository.

## Workflow Rules

- **NO CODE CHANGES WITHOUT APPROVAL** — discuss first, wait for approval
- **Always present complete files** — never partial diffs or patches
- **Increment version numbers** — bump header and update docstring changelog
- **Update README.md, STATUS.md, HANDOFF.md, README_ENV.md** alongside every code change
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
OPENAI_API_KEY=your_openai_key        # embeddings + classifier

# Conversation provider
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
MAX_RECENT_MESSAGES=5
```

Priority: shell env vars > `.env` file > `config.py` defaults.

## Architecture

### Message Flow
1. `main.py` → loads .env, creates bot, runs with DISCORD_TOKEN
2. `bot.py` → on_message routes to response pipeline or commands
3. First message in channel triggers `load_channel_history()` backfill
4. Addressed messages → `build_context_for_provider()` → `handle_ai_response()`
5. `raw_events.py` → persists every message to SQLite + embeds with OpenAI in parallel

### Semantic Retrieval (v4.0.0)
Every response context has two layers:
- **Always-on**: overview, key facts, open actions, open questions (from summary)
- **Retrieved**: latest user message embedded → top matching topics by cosine similarity
  → their linked messages injected as "PAST MESSAGES FROM THIS CHANNEL"

Topic-message linkage: after every `!summary create`, all active + archived topics are
embedded and linked to ALL messages above `TOPIC_LINK_MIN_SCORE` (0.3) by cosine similarity.

Fallback: if no topics score above `RETRIEVAL_MIN_SCORE` (0.3), full summary injected.

Key files: `utils/embedding_store.py` (embeddings, linking, retrieval),
`utils/context_manager.py` (always-on + retrieval + budget)

### Summarization Pipeline (v3.5+)
Both cold start and incremental use the same three-pass pipeline:
```
Raw messages + existing minutes
  → Secretary (Gemini, natural language minutes)
  → Structurer (Gemini, anyOf JSON schema)
  → Classifier (GPT-4o-mini, KEEP/DROP/RECLASSIFY + dedup)
  → apply_ops() → verify hashes → save
  → store topics + link to messages by embedding similarity
```

Key files: `summarizer.py` (router), `summarizer_authoring.py` (pipeline),
`summary_prompts_authoring.py` (Secretary/Structurer prompts),
`summary_delta_schema.py` (anyOf schema), `summary_classifier.py` (classifier)

### Noise Filtering
All bot output prefixed with ℹ️ (noise) or ⚙️ (settings persistence).
Filters in `message_processing.py`: `is_noise_message()`, `is_settings_message()`.

### Providers
- OpenAI, Anthropic, DeepSeek (conversation) — per-channel configurable
- Gemini (summarization Secretary/Structurer) — not used for conversation
- OpenAI GPT-4o-mini (classifier) — always used regardless of conversation provider
- OpenAI text-embedding-3-small (embeddings) — always used
- All providers: singleton cached, async executor wrapped

### Persistence
- SQLite with WAL mode (`data/messages.db`)
- Tables: messages, summaries, message_embeddings, topics, topic_messages
- `raw_events.py` captures all messages including bot responses + embeds them
- `db_migration.py` applies `schema/NNN.sql` files sequentially
- Settings recovered from Discord history on startup

## Key Design Decisions

- **Decision = agreement on action** — "I think X" / "Agreed" → decision.
  "What is X?" / "X is Y" → fact, NOT a decision.
- **Fresh-from-source > recursive** — Gemini's 1M context sends raw messages directly
- **Secretary writes freely** — no JSON constraint in Pass 1
- **Prefix-based filtering** — single ℹ️/⚙️ check replaces 30+ patterns
- **Hash protection** — SHA-256 on protected fields, supersession lifecycle
- **Threshold-based linking** — all messages above score threshold linked to topic, not top-N
- **Full budget for retrieval** — no pre-allocated slice; trimmer adjusts recent messages

## Commands Reference

| Command | Description |
|---------|-------------|
| `!summary` | Show channel summary |
| `!summary full/raw` | Full view / Secretary's raw minutes |
| `!summary create/clear` | Run summarization / delete (admin) |
| `!debug noise/cleanup/status` | Maintenance tools (admin) |
| `!debug backfill` | Embed missing messages + re-link all topics (admin) |
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
