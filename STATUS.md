# STATUS.md
# Discord Bot Development Status
# Version 3.2.3

## Current Version Features

### Version 3.2.3 - Summary Quality & Bot Message Filtering
- **ADDED**: `schema/003.sql` — `is_bot_author INTEGER DEFAULT 0` column migration
- **MODIFIED**: `utils/models.py` v1.2.0 — `is_bot_author: bool = False` field on StoredMessage
- **MODIFIED**: `utils/message_store.py` v1.2.0 — `is_bot_author` in INSERT and SELECT
  (column index 13); existing rows default to 0 via migration
- **MODIFIED**: `utils/raw_events.py` v1.2.0 — captures `message.author.bot` in
  persistence_on_message and _backfill_channel; bot responses stored with is_bot_author=True
- **MODIFIED**: `utils/summarizer.py` v1.5.0 — `not m.is_bot_author` filter in
  _get_unsummarized_messages() excludes all bot-authored messages (AI responses,
  trivia answers, etc.) from summarization input; resolves 130-fact noise problem
- **MODIFIED**: `utils/summarizer.py` v1.2.0–v1.4.0 (earlier in session) — batch loop:
  summarize_channel() loops over SUMMARIZER_BATCH_SIZE chunks until all messages processed;
  summary reloaded from DB each iteration so batches build on previous result;
  added housekeeping filters: is_history_output(), is_settings_persistence_message(),
  "System prompt updated for" excluded from summarizer (kept in channel_history)
- **MODIFIED**: `config.py` v1.10.0 — SUMMARIZER_BATCH_SIZE env var (default 200);
  GEMINI_MAX_TOKENS raised 8192 → 32768
- **MODIFIED**: `commands/summary_commands.py` v2.0.0 — !summarize removed; !summary
  becomes a group: `!summary` (show, all users), `!summary create` (run, admin),
  `!summary clear` (hard delete, admin)
- **MODIFIED**: `utils/summary_store.py` v1.1.0 — delete_channel_summary() added
- **MODIFIED**: `utils/summary_prompts.py` v1.1.0 — system prompt overhauled:
  durable-state-only promotion policy; explicit DO NOT PROMOTE list; budget guidance;
  PRIORITY ORDER for new items
- **MODIFIED**: `utils/summary_validation.py` v1.1.0 — content-empty add ops rejected;
  _CONTENT_OPS frozenset; check 0 before source ID check
- **MODIFIED**: `commands/__init__.py` v2.2.0 — !summarize removed from changelog

### Version 3.2.2 - Three-Layer Enforcement Architecture (SOW v3.2.0 full compliance)
- **MODIFIED**: `utils/summary_schema.py` v1.1.0 — DELTA_SCHEMA constant (ops[]
  JSON schema for Gemini response_json_schema); apply_updates() replaced by
  apply_ops() handling all 13 op types; verify_protected_hashes() unified to
  text_hash for all protected sections
- **MODIFIED**: `ai_providers/gemini_provider.py` v1.1.0 — response_mime_type
  and response_json_schema kwargs added to generate_ai_response(); passed to
  GenerateContentConfig as response_schema for Gemini Structured Outputs (Layer 1)
- **ADDED**: `utils/summary_normalization.py` v1.0.0 — parse_json_response()
  (3-strategy JSON extraction); classify_response() (delta/full/unknown);
  canonicalize_full_summary() (field remap + type coercion); diff_full_to_ops()
  (domain-aware diff of full summary → delta ops[]) — Layer 2 normalization
- **ADDED**: `utils/summary_validation.py` v1.0.0 — validate_domain(): source
  ID presence, duplicate ADD IDs within delta, ADD of pre-existing IDs, status
  transition validity — Layer 3 domain validation
- **ADDED**: `utils/summary_prompts.py` v1.0.0 — SYSTEM_PROMPT (SOW-specified
  strict instruction with forbidden example); build_label_map(); build_prompt()
  (hash-only CURRENT_STATE snapshot + M-labeled messages + RULES)
- **MODIFIED**: `utils/summarizer.py` v1.1.0 — full three-layer pipeline:
  Gemini Structured Outputs → normalization → domain validation → apply_ops;
  repair prompt retry on failure; imports from summary_prompts + summary_normalization
- **NOTE**: tier2_tests.py tests apply_updates() (old format) — needs update

### Version 3.2.1 - Gemini Provider + Summarizer Bugfix
- **ADDED**: `ai_providers/gemini_provider.py` v1.0.0 — GeminiProvider using
  google-genai SDK; converts OpenAI-style messages to Gemini format
  (system_instruction + contents); run_in_executor() pattern; usage logging
  from response.usage_metadata
- **MODIFIED**: `ai_providers/__init__.py` v1.4.0 — 'gemini' case in
  get_provider() factory; lazy import of GeminiProvider to avoid import errors
  when google-genai is not installed
- **MODIFIED**: `config.py` v1.9.0 — GEMINI_API_KEY, GEMINI_MODEL
  (gemini-2.5-flash-lite), GEMINI_CONTEXT_LENGTH (1M), GEMINI_MAX_TOKENS
  (8192); SUMMARIZER_PROVIDER default changed from AI_PROVIDER → 'gemini';
  SUMMARIZER_MODEL default changed to 'gemini-2.5-flash-lite'
- **MODIFIED**: `requirements.txt` — added google-genai>=1.0.0
- **MODIFIED**: `utils/summarizer.py` v1.0.1 — robust JSON extraction
  (3 strategies: direct, markdown fence strip, outermost { } block); logs
  full response (up to 1000 chars) on parse failure
- **MODIFIED**: `CLAUDE.md` v1.3.0 — added SOW compliance rule: never add
  limitations, caps, or behaviours not in the SOW without explicit approval
- **ADDED**: `tier2_tests.py` — 58 unit tests covering schema, store,
  summarizer functions (all pass)
- **NOTE**: GEMINI_API_KEY must be set in .env for !summarize to work

### Version 3.2.0 - Structured Summary Generation (Roadmap M2)
- **ADDED**: `utils/summary_schema.py` v1.0.0 — schema factory, hash utilities,
  update application, hash verification, source verification
- **ADDED**: `utils/summary_store.py` v1.0.0 — SQLite read/write for
  channel_summaries (placed here rather than message_store.py to stay under
  the 250-line limit)
- **ADDED**: `utils/summarizer.py` v1.0.0 — summarization engine: prompt
  building, LLM call, update application, integrity verification, persistence
- **ADDED**: `commands/summary_commands.py` v1.0.0 — !summarize (admin only)
  and !summary (all users) commands
- **MODIFIED**: `config.py` v1.8.0 — SUMMARIZER_PROVIDER, SUMMARIZER_MODEL
  (superseded by v1.9.0 in v3.2.1)
- **MODIFIED**: `commands/__init__.py` v2.1.0 — registers summary_commands
- **UNCHANGED**: message_store.py, bot.py, raw_events.py, all history modules,
  all existing providers — in-memory response pipeline untouched (M3 injects
  summary into prompts)

### Version 3.1.1 - Code Quality: realtime_settings_parser.py split
- **ADDED**: `utils/history/settings_appliers.py` v1.0.0 — individual setting
  applier functions extracted from realtime_settings_parser.py
- **MODIFIED**: `utils/history/realtime_settings_parser.py` v2.2.0 — now a thin
  orchestrator; imports helpers from settings_appliers.py; re-exports
  extract_prompt_from_update_message for backwards compatibility; 335→122 lines
- **FIXED**: HANDOFF.md branch/merge status corrected (development is at v3.1.0)
- **REASON**: realtime_settings_parser.py exceeded 250-line mandatory limit

### Version 3.1.0 - Schema Extension & Enhanced Capture
- **ADDED**: `schema/` directory with versioned SQL migration files
- **ADDED**: `schema/001.sql` — v3.0.0 baseline schema (extracted from message_store.py)
- **ADDED**: `schema/002.sql` — 5 new message columns, 2 new empty tables
- **ADDED**: `utils/db_migration.py` v1.0.0 — migration runner: scans schema/,
  applies unapplied migrations, tracks versions in schema_version table
- **MODIFIED**: `utils/models.py` v1.1.0 — StoredMessage gains 5 optional fields:
  reply_to_message_id, thread_id, edited_at, deleted_at, attachments_metadata
- **MODIFIED**: `utils/message_store.py` v1.1.0 — removed inline SCHEMA_SQL,
  calls run_migrations(), updated INSERT/SELECT for new columns,
  update_message_content() replaced by update_message_content_and_edit_time(),
  soft_delete_message() now sets deleted_at timestamp
- **MODIFIED**: `utils/raw_events.py` v1.1.0 — captures reply_to_message_id,
  thread_id, attachments_metadata on create and backfill; sets edited_at on edit
- **ADDED**: `channel_summaries` and `response_context_receipts` empty tables
  (populated by future milestones)

### Version 3.0.0 - SQLite Message Persistence Layer
- **ADDED**: `utils/models.py` v1.0.0 — StoredMessage dataclass for lightweight
  message representation (~350 bytes vs ~1,200 for discord.py Message objects)
- **ADDED**: `utils/message_store.py` v1.0.0 — SQLite database with WAL mode,
  insert/update/soft-delete/query operations, channel state tracking
- **ADDED**: `utils/raw_events.py` v1.0.2 — real-time message capture via
  on_message listener, raw edit/delete handlers, startup backfill
- **ADDED**: `DATABASE_PATH` env var (default `./data/messages.db`)
- **ADDED**: `data/` directory to .gitignore
- **FOUNDATION**: All messages persisted to SQLite in real-time, surviving
  restarts without API refetch. Foundation for future summarization subsystem.
- **FILES**: bot.py → v3.0.0, config.py → v1.7.0, models.py → v1.0.0,
  message_store.py → v1.0.0, raw_events.py → v1.0.2

### Version 2.23.0 - Token-Budget Context Management + Usage Logging
- **ADDED**: Provider-aware token budget ensures every API call fits within
  the active provider's context window regardless of message content size
- **ADDED**: `utils/context_manager.py` v1.0.0 — token counting via tiktoken,
  budget-aware context builder, per-channel usage accumulator
- **ADDED**: `CONTEXT_BUDGET_PERCENT` env var (default 80) — configurable
  percentage of context window used for input token budget
- **ADDED**: Per-call token usage logging (INFO) extracted from each provider's
  API response — actual prompt/completion tokens, not estimates
- **ADDED**: Per-channel cumulative token tracking (in-memory, resets on restart)
- **FIXED**: DeepSeek context length default 128000 → 64000 to match verified
  API endpoint limit (DeepSeek pricing-details page)
- **FIXED**: Response handler trims to MAX_HISTORY after assistant append
- **UPDATED**: Anthropic model default synced to `claude-haiku-4-5-20251001`
- **DEPENDENCY**: Added `tiktoken` for accurate token counting
- **FILES**: bot.py → v2.10.0, config.py → v1.6.0,
  response_handler.py → v1.1.4, context_manager.py → v1.0.0,
  openai_provider.py → v1.3.0, anthropic_provider.py → v1.1.0,
  openai_compatible_provider.py → v1.2.0

### Version 2.22.0 - Provider Singleton Caching
- **FIXED**: get_provider() now returns cached provider instances
- **FILE**: ai_providers/__init__.py → v1.3.0

### Version 2.21.0 - Async Executor Safety
- **FIXED**: Anthropic provider missing executor wrapper
- **FILES**: anthropic_provider.py → v1.0.0,
  openai_compatible_provider.py → v1.1.2

### Version 2.20.0 - DeepSeek Reasoning Content Display
- **FIXED**: DeepSeek reasoner `reasoning_content` now correctly extracted
- **FILES**: openai_compatible_provider.py → v1.1.1,
  response_handler.py → v1.1.3, message_processing.py → v2.2.6,
  thinking_commands.py → v2.1.0, ai_utils.py → v1.0.0

### Version 2.19.0 - History Noise Filtering (Runtime and Load-Time)
- **FIXED**: Bot output messages no longer pollute AI conversation context

### Version 2.18.0 - Continuous Context Accumulation
- **FIXED**: Regular messages now added to history regardless of auto-respond

### Version 2.17.0 - History Trim After Load
### Version 2.16.0 - Dead Code Cleanup
### Version 2.15.0 - Settings Persistence Fix (Fetch All)
### Version 2.14.0 - History Noise Cleanup
### Version 2.13.0 - Command Interface Redesign
### Version 2.12.0 - BaseTen Legacy Cleanup
### Version 2.11.0 - Provider Migration (74% cost reduction)
### Version 2.10.1 - OpenAI Heartbeat Fix
### Version 2.10.0 - Settings Persistence

---

## Success Metrics

### ✅ Achieved Metrics
- **Functionality**: Multi-provider AI support with seamless switching
- **Cost Optimization**: 74% cost reduction via DeepSeek Official API
- **Cost Visibility**: Per-call and cumulative token usage logged
- **Stability**: No heartbeat blocking — all providers use executor wrapper
- **Provider Efficiency**: Singleton caching prevents httpx RuntimeError
- **User Experience**: Consistent, intuitive command interface
- **Code Quality**: All files under 250 lines, excellent maintainability
- **Bounded API Context**: Token-budget ensures context window compliance
- **Clean API Context**: Noise filtered at runtime, load time, and API payload
- **Token Safety**: Every API call guaranteed to fit provider context window
- **Message Persistence**: All messages stored in SQLite, survives restarts

### 📈 Future Metrics
- **Context Continuity**: Fresh-from-source summarization via Gemini
- **Epoch Management**: Rollover for channels exceeding 25K messages
- **Cost Optimization**: Batch API + activity tiering

---

## Architecture Status

### Current File Structure
```
├── main.py                    # Entry point (minimal)
├── bot.py                     # Core Discord events (v3.0.0)
├── config.py                  # Configuration management (v1.9.0)
├── schema/                    # Versioned SQL migration files (NEW v3.1.0)
│   ├── 001.sql                    # v3.0.0 baseline schema
│   └── 002.sql                    # v3.1.0 extensions
├── commands/                  # Modular command system
│   ├── __init__.py
│   ├── history_commands.py
│   ├── prompt_commands.py
│   ├── ai_provider_commands.py
│   ├── auto_respond_commands.py
│   ├── thinking_commands.py       # v2.1.0
│   └── status_commands.py
├── ai_providers/              # AI provider implementations
│   ├── __init__.py                # Provider factory (v1.4.0)
│   ├── base.py
│   ├── openai_provider.py         # v1.3.0
│   ├── anthropic_provider.py      # v1.1.0
│   ├── openai_compatible_provider.py  # v1.2.0
│   └── gemini_provider.py         # v1.0.0 (NEW v3.2.1)
└── utils/                     # Utility modules
    ├── models.py                  # v1.1.0 — StoredMessage dataclass
    ├── message_store.py           # v1.1.0 — SQLite persistence
    ├── raw_events.py              # v1.1.0 — message capture + backfill
    ├── db_migration.py            # v1.0.0 (NEW — migration runner)
    ├── ai_utils.py                # v1.0.0
    ├── context_manager.py         # v1.0.0
    ├── logging_utils.py
    ├── message_utils.py
    ├── provider_utils.py
    ├── response_handler.py        # v1.1.4
    └── history/
        ├── __init__.py
        ├── storage.py
        ├── prompts.py
        ├── message_processing.py  # v2.2.6
        ├── discord_loader.py      # v2.1.0
        ├── discord_converter.py   # v1.0.1
        ├── discord_fetcher.py     # v1.2.0
        ├── realtime_settings_parser.py  # v2.2.0
        ├── settings_appliers.py         # v1.0.0 (NEW v3.1.1)
├── utils/                     # Utility modules (continued)
│   ├── summary_schema.py          # v1.0.0 (NEW v3.2.0)
│   ├── summary_store.py           # v1.0.0 (NEW v3.2.0)
│   └── summarizer.py              # v1.0.1 (NEW v3.2.0, bugfix v3.2.1)
└── commands/                  # (continued)
    └── summary_commands.py        # v1.0.0 (NEW v3.2.0)
        ├── settings_manager.py
        ├── cleanup_coordinator.py # v2.2.0
        ├── channel_coordinator.py
        ├── loading.py             # v2.4.0
        ├── loading_utils.py       # v1.2.0
        ├── api_imports.py         # v1.3.0
        ├── api_exports.py         # v1.3.0
        ├── management_utilities.py
        └── diagnostics.py
```

### Architecture Quality Standards
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

---

## Current Priority Issues

### 1. Next — Gemini Summarization Integration
**Status**: Design phase — depends on v3.1.0 schema layer
**Design**: Fresh-from-source summarization using Gemini 2.5 Flash Lite

### Resolved Issues
- ✅ Schema migration infrastructure — resolved in v3.1.0
- ✅ Enhanced message capture (replies, threads, attachments) — resolved in v3.1.0
- ✅ Message persistence — resolved in v3.0.0
- ✅ Token-based context trimming — resolved in v2.23.0
- ✅ Token usage visibility — resolved in v2.23.0
- ✅ DeepSeek context length default wrong — resolved in v2.23.0
- ✅ Anthropic model default stale — resolved in v2.23.0
- ✅ Provider singleton caching — resolved in v2.22.0
- ✅ Anthropic heartbeat blocking risk — resolved in v2.21.0
- ✅ DeepSeek reasoning_content display — resolved in v2.20.0
- ✅ Runtime and load-time history noise filtering — resolved in v2.19.0
- ✅ Continuous context accumulation — resolved in v2.18.0
- ✅ Unbounded API context — resolved in v2.17.0
- ✅ Dead code cleanup — resolved in v2.16.0
- ✅ Settings persistence (fetch limit) — resolved in v2.15.0
- ✅ History noise at load time — resolved in v2.14.0
- ✅ Command interface inconsistencies — resolved in v2.13.0
- ✅ BaseTen legacy code — resolved in v2.12.0
- ✅ Provider cost and rate limiting — resolved in v2.11.0
- ✅ Discord heartbeat blocking (OpenAI) — resolved in v2.10.1
- ✅ Settings persistence (initial) — resolved in v2.10.0
