# STATUS.md
# Discord Bot Development Status
# Version 3.3.2

## Current Version Features

### Version 3.3.2 - Debug Command Group
- **ADDED**: `commands/debug_commands.py` v1.0.0 — `!debug noise/cleanup/status`
  consolidates maintenance and diagnostic tools
- **MODIFIED**: `commands/__init__.py` v2.4.0 — registers debug_commands,
  removes cleanup_commands
- **REMOVED**: `commands/cleanup_commands.py` — functionality moved to !debug

### Version 3.3.1 - Supersession Fix + Readable Snapshots
- **MODIFIED**: `utils/summary_schema.py` v1.4.0 — `_supersede()` always retires
  old decision even with empty text; fixes both decisions staying active
- **MODIFIED**: `utils/summary_prompts.py` v1.5.0 — snapshot includes readable
  text (decision, fact, task, question) so model can match existing IDs for
  supersede ops; added "use EXACT id from CURRENT_STATE" rule; re-exports
  authoring prompts
- **MODIFIED**: `utils/summary_prompts_authoring.py` v1.1.2 — M-labels added
  to WHAT TO SKIP list in Secretary prompt
- **TESTED**: Three successive decision changes (Redis → SQLite → PostgreSQL)
  all correctly superseded with stable token counts (~1,500)

### Version 3.3.0 - Two-Pass Summarization + Prefix Noise Filtering
- **ADDED**: `utils/summary_prompts_authoring.py` v1.1.1 — Secretary (natural
  language minutes) + Structurer (JSON conversion) prompts. Decision defined
  as agreement-on-action, not fact lookup.
- **ADDED**: `utils/summarizer_authoring.py` v1.0.1 — Cold start two-pass
  pipeline: Secretary writes unstructured minutes, Structurer converts to
  JSON delta ops. Single-pass (no batching) for cold starts.
- **ADDED**: `utils/summary_display.py` v1.1.0 — Paginated Discord output
  with ℹ️ prefix on all pages
- **ADDED**: `commands/cleanup_commands.py` v1.0.0 — `!cleanup scan/run` for
  removing pre-prefix bot noise from Discord history (later moved to !debug)
- **MODIFIED**: `commands/summary_commands.py` v2.2.0 — ℹ️ prefix on all output;
  `!summary raw` and `!summary full` subcommands
- **MODIFIED**: `utils/summarizer.py` v1.9.0 — routes cold starts to Secretary
  pipeline, incremental updates to delta ops
- **MODIFIED**: `utils/summary_prompts.py` v1.3.0→v1.5.0 — re-exports authoring
  prompts; readable text in snapshots
- **MODIFIED**: All command modules — ℹ️/⚙️ prefix system:
  - `commands/auto_respond_commands.py` v2.1.0
  - `commands/ai_provider_commands.py` v2.1.0
  - `commands/thinking_commands.py` v2.2.0
  - `commands/prompt_commands.py` v2.1.0
  - `commands/status_commands.py` v2.1.0
  - `commands/history_commands.py` v2.1.0
- **MODIFIED**: `utils/history/message_processing.py` v2.3.0 — prefix-based
  filters (`is_noise_message()`, `is_settings_message()`, `is_admin_output()`)
  replace growing pattern-match list; legacy patterns retained for backward compat
- **RESULT**: Cold start: 18,619 tokens → 1,871 tokens for 483 messages.
  214 items → ~15 meaningful entries. 1 real decision instead of 40+ facts.

### Version 3.2.3 - Summary Quality & Bot Message Filtering
- **ADDED**: `schema/003.sql` — `is_bot_author INTEGER DEFAULT 0` column
- **MODIFIED**: `utils/models.py` v1.2.0 — `is_bot_author` field on StoredMessage
- **MODIFIED**: `utils/message_store.py` v1.2.0 — `is_bot_author` in INSERT/SELECT
- **MODIFIED**: `utils/raw_events.py` v1.2.0 — captures `message.author.bot`
- **MODIFIED**: `utils/summarizer.py` v1.5.0 — `not m.is_bot_author` filter
- **MODIFIED**: `config.py` v1.10.0 — SUMMARIZER_BATCH_SIZE, GEMINI_MAX_TOKENS
- **MODIFIED**: `commands/summary_commands.py` v2.0.0 — !summary group
- **MODIFIED**: `utils/summary_prompts.py` v1.1.0 — durable-state promotion policy
- **MODIFIED**: `utils/summary_validation.py` v1.1.0 — content-empty ops rejected

### Version 3.2.2 - Three-Layer Enforcement Architecture
- **MODIFIED**: `utils/summary_schema.py` v1.1.0 — DELTA_SCHEMA, apply_ops()
- **MODIFIED**: `ai_providers/gemini_provider.py` v1.1.0 — Structured Outputs
- **ADDED**: `utils/summary_normalization.py` v1.0.0 — parse, classify, canonicalize
- **ADDED**: `utils/summary_validation.py` v1.0.0 — domain validation
- **ADDED**: `utils/summary_prompts.py` v1.0.0 — SYSTEM_PROMPT, build_prompt()
- **MODIFIED**: `utils/summarizer.py` v1.1.0 — full pipeline wired

### Version 3.2.0 - Structured Summary Generation (Roadmap M2)
- **ADDED**: `utils/summary_schema.py` v1.0.0 — schema, hash, ops
- **ADDED**: `utils/summary_store.py` v1.0.0 — SQLite channel_summaries
- **ADDED**: `utils/summarizer.py` v1.0.0 — summarization engine
- **ADDED**: `commands/summary_commands.py` v1.0.0 — !summarize and !summary
- **MODIFIED**: `config.py` v1.8.0 — SUMMARIZER_PROVIDER, SUMMARIZER_MODEL

### Version 3.1.1 - Code Quality: realtime_settings_parser.py split
- **ADDED**: `utils/history/settings_appliers.py` v1.0.0
- **MODIFIED**: `utils/history/realtime_settings_parser.py` v2.2.0

### Version 3.1.0 - Schema Extension & Enhanced Capture
- **ADDED**: `schema/001.sql`, `schema/002.sql`, `utils/db_migration.py` v1.0.0
- **MODIFIED**: `utils/models.py` v1.1.0, `utils/message_store.py` v1.1.0
- **MODIFIED**: `utils/raw_events.py` v1.1.0, `bot.py` v3.1.0, `config.py` v1.9.0

### Version 3.0.0 - SQLite Message Persistence Layer
- **ADDED**: `utils/models.py`, `utils/message_store.py`, `utils/raw_events.py`
- SQLite with WAL mode, real-time capture, startup backfill

### Version 2.23.0 - Token-Budget Context Management + Usage Logging
### Version 2.22.0 - Provider Singleton Caching
### Version 2.21.0 - Async Executor Safety
### Version 2.20.0 - DeepSeek Reasoning Content Display
### Version 2.19.0 - Runtime History Noise Filtering
### Version 2.18.0 - Continuous Context Accumulation
### Version 2.17.0 - Unbounded API Context Fix
### Version 2.16.0 - Dead Code Cleanup
### Version 2.15.0 - Settings Persistence (Fetch Limit)
### Version 2.14.0 - History Noise at Load Time
### Version 2.13.0 - Command Interface Redesign

---

## Project File Tree (current versions)

```
discord-bot/
├── bot.py                         # v3.1.0
├── config.py                      # v1.10.0
├── main.py
├── .env
├── data/
│   └── messages.db                # SQLite + WAL
├── schema/
│   ├── 001.sql                    # v3.0.0 baseline
│   ├── 002.sql                    # v3.1.0 columns + tables
│   └── 003.sql                    # v3.2.3 is_bot_author
├── ai_providers/
│   ├── __init__.py                # v1.4.0
│   ├── openai_provider.py         # v1.3.0
│   ├── anthropic_provider.py      # v1.1.0
│   ├── openai_compatible_provider.py  # v1.2.0
│   └── gemini_provider.py         # v1.1.0
├── commands/
│   ├── __init__.py                # v2.4.0
│   ├── auto_respond_commands.py   # v2.1.0
│   ├── ai_provider_commands.py    # v2.1.0
│   ├── thinking_commands.py       # v2.2.0
│   ├── prompt_commands.py         # v2.1.0
│   ├── status_commands.py         # v2.1.0
│   ├── history_commands.py        # v2.1.0
│   ├── summary_commands.py        # v2.2.0
│   └── debug_commands.py          # v1.0.0
├── utils/
│   ├── models.py                  # v1.2.0
│   ├── message_store.py           # v1.2.0
│   ├── raw_events.py              # v1.2.0
│   ├── db_migration.py            # v1.0.0
│   ├── context_manager.py         # v1.0.0
│   ├── response_handler.py        # v1.1.4
│   ├── summarizer.py              # v1.9.0
│   ├── summarizer_authoring.py    # v1.0.1
│   ├── summary_schema.py          # v1.4.0
│   ├── summary_store.py           # v1.1.0
│   ├── summary_prompts.py         # v1.5.0
│   ├── summary_prompts_authoring.py  # v1.1.2
│   ├── summary_display.py         # v1.1.0
│   ├── summary_normalization.py   # v1.0.0
│   ├── summary_validation.py      # v1.1.0
│   └── history/
│       ├── __init__.py
│       ├── storage.py
│       ├── prompts.py
│       ├── message_processing.py  # v2.3.0
│       ├── discord_loader.py      # v2.1.0
│       ├── discord_converter.py   # v1.0.1
│       ├── discord_fetcher.py     # v1.2.0
│       ├── realtime_settings_parser.py  # v2.2.0
│       └── settings_appliers.py   # v1.0.0
└── docs/
    └── sow/                       # Design documents
```

---

## Architecture Quality Standards
1. **250-line file limit** - Mandatory for all files
2. **Single responsibility** - Each module serves one clear purpose
3. **Comprehensive documentation** - Detailed docstrings and inline comments
4. **Module-specific logging** - Structured logging with appropriate levels
5. **Error handling** - Graceful degradation and proper error recovery
6. **Version tracking** - Proper version numbers and changelogs in all files
7. **Async safety** - All provider API calls wrapped in run_in_executor()
8. **Provider efficiency** - Singleton caching prevents unnecessary instantiation
9. **Token safety** - Every API call budget-checked against provider context window
10. **Message persistence** - All messages stored in SQLite via on_message listener
11. **Prefix tagging** - All bot output tagged ℹ️ (noise) or ⚙️ (settings)

---

## Resolved Issues
- ✅ Summarization quality — resolved in v3.3.0 (Secretary architecture)
- ✅ Decision supersession — resolved in v3.3.1
- ✅ Summary output contamination — resolved in v3.3.0 (prefix system)
- ✅ Bot message noise in summaries — resolved in v3.2.3
- ✅ Structured output too rigid — resolved in v3.3.0 (two-pass)
- ✅ Message persistence — resolved in v3.0.0
- ✅ Token-based context trimming — resolved in v2.23.0
- ✅ Provider singleton caching — resolved in v2.22.0
- ✅ Async executor safety — resolved in v2.21.0
- ✅ Runtime/load-time noise filtering — resolved in v2.19.0
- ✅ Command interface redesign — resolved in v2.13.0

## Current Priority Issues

### 1. M3: Context Integration (NEXT)
Inject summary minutes into `build_context_for_provider()` between system
prompt and recent messages so the bot uses its conversational memory.

### 2. Incremental Path Quality
Token growth from incremental updates needs monitoring. Consider collapsing
to always use Secretary path instead of delta ops for all updates.

### 3. WAL File Stats Bug
`get_database_stats()` reports 0.0 MB because it only measures the main
SQLite file, not the WAL file which holds the actual data.
