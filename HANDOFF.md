# HANDOFF.md
# Version 3.0.0
# Agent Development Handoff Document

## Current Status

**Branch**: development
**Tag**: v2.23.0 on main (v3.0.0 not yet merged)
**Bot**: Running on systemd, stable, using deepseek-reasoner model
**Last completed**: v3.0.0 — SQLite Message Persistence Layer
**Next**: v3.1.0 — Gemini Summarization Integration

---

## Recent Completed Work

### v3.0.0 — SQLite Message Persistence Layer
- **NEW**: `utils/models.py` v1.0.0 — StoredMessage dataclass (~350 bytes
  per instance vs ~1,200 for discord.py Message objects)
- **NEW**: `utils/message_store.py` v1.0.0 — SQLite with WAL mode, schema
  creation, insert/update/soft-delete/query, channel state tracking
- **NEW**: `utils/raw_events.py` v1.0.2 — on_message listener for real-time
  capture (including bot messages), raw edit/delete handlers, startup backfill
  with Semaphore(3) concurrency limit and 10K message cap per channel
- **MODIFIED**: `bot.py` v3.0.0 — imports raw_events, calls setup_raw_events()
  and startup_backfill() in on_ready()
- **MODIFIED**: `config.py` v1.7.0 — added DATABASE_PATH env var
- **MODIFIED**: `.gitignore` — added `data/`
- **NEW**: `docs/sow/SOW_v3.0.0.md`
- **VERIFIED**: Database creation, WAL mode, real-time capture (create/edit/
  delete), startup backfill, restart recovery, no impact on existing response
  pipeline. 3,200+ messages captured across 12 channels.

**Key bug fixes during development:**
- v1.0.0 → v1.0.1: `@bot.event` → `bot.add_listener()` for event registration
- v1.0.1 → v1.0.2: `on_raw_message_create` not dispatched by `commands.Bot`
  when `@bot.event on_message` is defined. Replaced with a second `on_message`
  listener registered via `bot.add_listener(persistence_on_message, 'on_message')`.

### v2.23.0 — Token-Budget Context Management + Usage Logging
- **Files**: bot.py → v2.10.0, config.py → v1.6.0,
  context_manager.py → v1.0.0, response_handler.py → v1.1.4,
  openai_provider.py → v1.3.0, anthropic_provider.py → v1.1.0,
  openai_compatible_provider.py → v1.2.0

### v2.22.0 — Provider Singleton Caching
- **File**: ai_providers/__init__.py → v1.3.0

### v2.21.0 — Async Executor Safety
### v2.20.0 — DeepSeek Reasoning Content Display

---

## v3.x Roadmap

### v3.1.0 — Gemini Summarization Integration (NEXT)
- Add Gemini 2.5 Flash Lite as summarization-only provider
- Incremental summarization: every 15-30 messages, Gemini generates
  structured meeting-minutes-style summary from raw messages in SQLite
- Fresh-from-source: send raw messages directly (no recursive summary-of-
  summary), eliminating the 14% semantic drift per cycle documented in
  research. Gemini's 1M token context fits ~25,000 raw messages.
- Summary injected into response context between system prompt and recent
  messages via existing build_context_for_provider() injection point
- Estimated new files: summarizer.py, gemini_client.py

### v3.2.0 — Epoch Rollover + Fresh Recalibration
- When channel exceeds ~25,000 messages, freeze current summary as an
  archived epoch artifact and reset the active summarization window
- Weekly fresh-from-source recalibration pass via Gemini Batch API (50%
  discount) to reset any accumulated drift in incremental summaries
- Archived epoch summaries are tiny (~800 tokens each) and stack in
  the response context for long-term channel memory

### v3.3.0 — Cost Optimization + Activity Tiering
- Batch API integration for scheduled recalibration passes
- Activity-based summarization frequency: hot channels every 50 messages,
  warm every 100, cold every 200, dormant channels skip entirely
- Implicit context caching optimization (stable prefix structure)

---

## SQLite Persistence Architecture (v3.0.0)

### Database Location
Default: `./data/messages.db` (configurable via `DATABASE_PATH` env var)

### Schema
```sql
messages: id (PK), channel_id, author_id, author_name, content,
          created_at, message_type, is_deleted
channel_state: channel_id (PK), last_processed_id, updated_at
Indexes: idx_channel_time, idx_channel_id
```

### Event Flow
```
Discord Gateway → on_message listener (raw_events.py)
                    → asyncio.to_thread(insert_message)
                    → asyncio.to_thread(update_last_processed_id)

Discord Gateway → on_raw_message_edit (raw_events.py)
                    → asyncio.to_thread(update_message_content)

Discord Gateway → on_raw_message_delete (raw_events.py)
                    → asyncio.to_thread(soft_delete_message)

Bot startup → on_ready() → startup_backfill()
                → per-channel: fetch after last_processed_id
                → Semaphore(3) concurrency, 10K cap per channel
```

### Key Design Decisions
- **on_message listener** (not on_raw_message_create): `commands.Bot` does
  not dispatch `on_raw_message_create` when `@bot.event on_message` is
  defined. The persistence listener is a second `on_message` registered
  via `bot.add_listener()` which coexists with bot.py's primary handler.
- **Bot messages stored**: Unlike bot.py's `on_message` which skips bot
  messages, the persistence listener captures them — they are conversation
  context needed for summarization.
- **Soft delete**: Deleted messages set `is_deleted = 1`, never hard-deleted.
  Removing messages creates conversational gaps that confuse summarization.
- **WAL mode**: Enables concurrent reads during writes — critical for async
  bot that receives messages while summarization reads the database.
- **asyncio.to_thread()**: All SQLite operations run off the event loop to
  prevent blocking Discord's heartbeat.

---

## Token Budget + Usage Architecture (v2.23.0)

### Call Flow
```
bot.py on_message()
  → get_provider(provider_override, channel_id)
  → build_context_for_provider(channel_id, provider)
      → prepare_messages_for_api(channel_id)
      → estimate_tokens() per message
      → newest-to-oldest until budget exhausted
      → return [system_msg] + selected
  → handle_ai_response(message, channel_id, messages, provider_override)
      → generate_ai_response(messages, ...)
      → provider._log_usage(response, channel_id) OR inline extraction
      → record_usage(channel_id, provider, in, out)
```

### Noise Filtering Architecture (Three Layers)
```
Layer 1 — Runtime:   add_response_to_history() checks is_history_output()
Layer 2 — Load time: discord_converter.py checks is_history_output()
Layer 3 — API build: prepare_messages_for_api() checks is_history_output()
                     AND is_settings_persistence_message()
```

### Constants That Must Stay in Sync

| Constant | Files |
|----------|-------|
| `API_ERROR_PREFIX` | response_handler.py, message_processing.py |
| `REASONING_PREFIX` | openai_compatible_provider.py, response_handler.py, message_processing.py |
| `REASONING_SEPARATOR` | openai_compatible_provider.py, response_handler.py |

---

## Current .env Configuration
```
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=sk-[key]
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-reasoner
OPENAI_COMPATIBLE_CONTEXT_LENGTH=64000
OPENAI_COMPATIBLE_MAX_TOKENS=8000
CONTEXT_BUDGET_PERCENT=80
```

---

## Development Rules (from AGENT.md)
1. NO CODE CHANGES WITHOUT APPROVAL
2. ALL DEVELOPMENT WORK IN development BRANCH
3. main BRANCH IS FOR STABLE CODE ONLY
4. DISCUSS FIRST, CODE SECOND
5. ALWAYS provide full files — no partial patches
6. INCREMENT version numbers in file heading comments
7. Keep files under 250 lines
8. Test before committing
9. Update STATUS.md and HANDOFF.md with every commit
