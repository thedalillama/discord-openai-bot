# HANDOFF.md
# Version 3.2.3
# Agent Development Handoff Document

## Current Status

**Branch**: claude-code (v3.2.3 not yet merged to development)
**Main**: v3.0.0 (untagged)
**Development**: v3.1.1
**Bot**: Running on systemd, stable, using deepseek-reasoner model
**Last completed**: v3.2.3 — Summary quality improvements + is_bot_author filtering
**Next**: M3 — Inject summary into response context (build_context_for_provider)
**Env required**: GEMINI_API_KEY in .env; restart bot to pick up schema/003.sql migration

---

## Recent Completed Work

### v3.2.3 — Summary Quality & Bot Message Filtering
- **NEW**: `schema/003.sql` — `ALTER TABLE messages ADD COLUMN is_bot_author INTEGER DEFAULT 0`
- **MODIFIED**: `utils/models.py` v1.2.0 — `is_bot_author: bool = False` on StoredMessage
- **MODIFIED**: `utils/message_store.py` v1.2.0 — INSERT/SELECT include is_bot_author (col 13)
- **MODIFIED**: `utils/raw_events.py` v1.2.0 — `message.author.bot` captured in realtime
  and backfill; bot responses stored with is_bot_author=True
- **MODIFIED**: `utils/summarizer.py` v1.5.0 — `not m.is_bot_author` filter added to
  _get_unsummarized_messages(); resolves 130-fact noise from AI-generated trivia answers
- **MODIFIED**: `utils/summarizer.py` v1.2.0–v1.4.0 — batch loop over SUMMARIZER_BATCH_SIZE;
  housekeeping filters (is_history_output, is_settings_persistence_message,
  "System prompt updated for"); _partial() return helper
- **MODIFIED**: `config.py` v1.10.0 — SUMMARIZER_BATCH_SIZE (default 200);
  GEMINI_MAX_TOKENS 8192 → 32768
- **MODIFIED**: `commands/summary_commands.py` v2.0.0 — !summary group: show / create / clear;
  !summarize removed
- **MODIFIED**: `utils/summary_store.py` v1.1.0 — delete_channel_summary() added
- **MODIFIED**: `utils/summary_prompts.py` v1.1.0 — durable-state-only system prompt;
  DO NOT PROMOTE list; PRIORITY ORDER; 0-3 item budget per batch
- **MODIFIED**: `utils/summary_validation.py` v1.1.0 — content-empty add ops rejected
- **MODIFIED**: `commands/__init__.py` v2.2.0

### v3.2.2 — Three-Layer Enforcement Architecture
- **MODIFIED**: `utils/summary_schema.py` v1.1.0 — DELTA_SCHEMA (ops[] JSON
  schema for Gemini response_json_schema); apply_ops() replaces apply_updates();
  text_hash unified across all protected sections
- **MODIFIED**: `ai_providers/gemini_provider.py` v1.1.0 — response_mime_type +
  response_json_schema kwargs → GenerateContentConfig.response_schema (Layer 1)
- **NEW**: `utils/summary_normalization.py` v1.0.0 — parse_json_response(),
  classify_response(), canonicalize_full_summary(), diff_full_to_ops() (Layer 2)
- **NEW**: `utils/summary_validation.py` v1.0.0 — validate_domain(): source IDs,
  duplicate ADD IDs, pre-existing ID ADDs, status transitions (Layer 3)
- **NEW**: `utils/summary_prompts.py` v1.0.0 — SYSTEM_PROMPT, build_label_map(),
  build_prompt() with hash-only CURRENT_STATE snapshot
- **MODIFIED**: `utils/summarizer.py` v1.1.0 — full three-layer pipeline wired;
  Gemini Structured Outputs; repair prompt retry; imports from new modules
- **NOTE**: tier2_tests.py tests apply_updates() (old format) — needs update

### v3.2.1 — Gemini Provider + Summarizer Bugfix
- **NEW**: `ai_providers/gemini_provider.py` v1.0.0 — GeminiProvider; google-genai
  SDK (pip: google-genai); converts OpenAI-style messages to Gemini format
  (system → system_instruction, user/assistant → contents with role "user"/"model");
  run_in_executor() pattern; usage from response.usage_metadata
- **NEW**: `tier2_tests.py` — 58 unit tests, all pass
- **MODIFIED**: `ai_providers/__init__.py` v1.4.0 — 'gemini' case added to
  get_provider() factory with lazy import of GeminiProvider
- **MODIFIED**: `config.py` v1.9.0 — GEMINI_API_KEY, GEMINI_MODEL
  (gemini-2.5-flash-lite), GEMINI_CONTEXT_LENGTH (1000000), GEMINI_MAX_TOKENS
  (8192); SUMMARIZER_PROVIDER default → 'gemini'; SUMMARIZER_MODEL → same
- **MODIFIED**: `requirements.txt` — added google-genai>=1.0.0
- **MODIFIED**: `utils/summarizer.py` v1.0.1 — _parse_json_response() with 3
  strategies (direct, markdown fence, outermost {}) to handle LLM prose wrapping
- **MODIFIED**: `CLAUDE.md` v1.3.0 — SOW compliance rule: never add limitations
  not in the SOW without approval

### v3.2.0 — Structured Summary Generation (Roadmap M2)
- **NEW**: `utils/summary_schema.py` v1.0.0 — schema factory, compute_hash,
  apply_updates, verify_protected_hashes, run_source_verification
- **NEW**: `utils/summary_store.py` v1.0.0 — save_channel_summary,
  get_channel_summary (placed here rather than message_store.py due to 250-line
  limit; imports _get_conn from message_store via deferred import)
- **NEW**: `utils/summarizer.py` v1.0.0 — summarize_channel() orchestrator;
  M-label system for source tracing; loop.run_in_executor() via provider;
  asyncio.to_thread() for SQLite
- **NEW**: `commands/summary_commands.py` v1.0.0 — !summarize (admin) and
  !summary (all users)
- **MODIFIED**: `config.py` v1.8.0 — SUMMARIZER_PROVIDER, SUMMARIZER_MODEL
- **MODIFIED**: `commands/__init__.py` v2.1.0 — registers summary_commands
- **NOTE**: SUMMARIZER_MODEL is meta-only in v1.0.0; provider uses its
  configured model (per-call model override requires provider refactor, deferred)

### v3.1.1 — Code Quality: realtime_settings_parser.py split
- **NEW**: `utils/history/settings_appliers.py` v1.0.0 — extracted 5 helper
  functions (_parse_and_apply_* × 4 + extract_prompt_from_update_message)
- **MODIFIED**: `utils/history/realtime_settings_parser.py` v2.2.0 — thin
  orchestrator only; imports from settings_appliers; re-exports
  extract_prompt_from_update_message for backwards compatibility; 335→122 lines
- **FIXED**: HANDOFF.md corrected to show development is at v3.1.0

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
          attachments_metadata, is_bot_author
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
schema/003.sql  — v3.2.3 is_bot_author column
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
- **Bot messages stored with is_bot_author flag**: Unlike bot.py's `on_message`
  which skips bot messages, the persistence listener captures them with
  `is_bot_author=True`. The summarizer excludes them via `not m.is_bot_author`
  filter — allowing future use (e.g. context display) while keeping
  AI-generated content out of the summarization input.
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
