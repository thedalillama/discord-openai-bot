# HANDOFF.md
# Version 3.1.0
# Agent Development Handoff Document

## Current Status

**Branch**: development
**Tag**: v2.23.0 on main (v3.0.0 and v3.1.0 not yet merged)
**Bot**: Running on systemd, stable, using deepseek-reasoner model
**Last completed**: v3.1.0 — Schema Extension & Enhanced Capture
**Next**: Gemini Summarization Integration

---

## Recent Completed Work

### v3.1.0 — Schema Extension & Enhanced Capture
- **NEW**: `schema/001.sql` — v3.0.0 baseline schema extracted from message_store.py
- **NEW**: `schema/002.sql` — 5 new message columns, 2 new empty tables
- **NEW**: `utils/db_migration.py` v1.0.0 — scans schema/, applies unapplied
  migrations sequentially, tracks each in schema_version table. Idempotent.
- **MODIFIED**: `utils/models.py` v1.1.0 — StoredMessage adds 5 optional fields:
  reply_to_message_id, thread_id, edited_at, deleted_at, attachments_metadata
- **MODIFIED**: `utils/message_store.py` v1.1.0 — removed SCHEMA_SQL, calls
  run_migrations(), updated INSERT/SELECT for 3 new capture fields,
  replaced update_message_content() with update_message_content_and_edit_time(),
  soft_delete_message() now also sets deleted_at
- **MODIFIED**: `utils/raw_events.py` v1.1.0 — persistence_on_message and
  _backfill_channel capture reply_to_message_id, thread_id, attachments_metadata;
  on_raw_message_edit calls update_message_content_and_edit_time()
- **NEW**: `docs/sow/SOW_v3.1.0.md`

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

**Key bug fixes during v3.0.0 development:**
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

### Next — Gemini Summarization Integration
- Add Gemini 2.5 Flash Lite as summarization-only provider
- Incremental summarization: every 15-30 messages, Gemini generates
  structured meeting-minutes-style summary from raw messages in SQLite
- Fresh-from-source: send raw messages directly (no recursive summary-of-
  summary), eliminating the 14% semantic drift per cycle documented in
  research. Gemini's 1M token context fits ~25,000 raw messages.
- Summary injected into response context between system prompt and recent
  messages via existing build_context_for_provider() injection point
- channel_summaries table (created in v3.1.0) is the write target
- Estimated new files: summarizer.py, gemini_client.py

### Future — Epoch Rollover + Fresh Recalibration
- When channel exceeds ~25,000 messages, freeze current summary as an
  archived epoch artifact and reset the active summarization window
- Weekly fresh-from-source recalibration pass via Gemini Batch API (50%
  discount) to reset any accumulated drift in incremental summaries

### Future — Cost Optimization + Activity Tiering
- Batch API integration for scheduled recalibration passes
- Activity-based summarization frequency: hot channels every 50 messages,
  warm every 100, cold every 200, dormant channels skip entirely

---

## SQLite Persistence Architecture (v3.1.0)

### Database Location
Default: `./data/messages.db` (configurable via `DATABASE_PATH` env var)

### Schema
```sql
messages: id (PK), channel_id, author_id, author_name, content,
          created_at, message_type, is_deleted,
          reply_to_message_id, thread_id, edited_at, deleted_at,
          attachments_metadata
channel_state: channel_id (PK), last_processed_id, updated_at
channel_summaries: channel_id (PK), summary_json, updated_at,
                   message_count, last_message_id
response_context_receipts: response_message_id (PK), user_message_id,
                           channel_id, created_at, receipt_json
schema_version: version (PK), applied_at
Indexes: idx_channel_time, idx_channel_id, idx_reply_to, idx_thread,
         idx_receipt_channel
```

### Migration Architecture
```
schema/001.sql  — v3.0.0 baseline
schema/002.sql  — v3.1.0 extensions
schema/NNN.sql  — future migrations (add files, runner picks them up)

init_database() → run_migrations(conn)
                    → CREATE TABLE IF NOT EXISTS schema_version
                    → scan schema/ for NNN.sql files
                    → apply unapplied in sequence
                    → record each in schema_version
```

### Event Flow
```
Discord Gateway → on_message listener (raw_events.py)
                    → asyncio.to_thread(insert_message)
                    → asyncio.to_thread(update_last_processed_id)

Discord Gateway → on_raw_message_edit (raw_events.py)
                    → asyncio.to_thread(update_message_content_and_edit_time)

Discord Gateway → on_raw_message_delete (raw_events.py)
                    → asyncio.to_thread(soft_delete_message)  # sets deleted_at

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
- **Soft delete**: Deleted messages set `is_deleted = 1` and `deleted_at`
  timestamp, never hard-deleted. Removing messages creates conversational
  gaps that confuse summarization.
- **WAL mode**: Enables concurrent reads during writes — critical for async
  bot that receives messages while summarization reads the database.
- **asyncio.to_thread()**: All SQLite operations run off the event loop to
  prevent blocking Discord's heartbeat.
- **Migration runner**: Adding future tables requires only a new NNN.sql file.
  No code changes to message_store.py or db_migration.py.

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
