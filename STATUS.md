# STATUS.md
# Discord Bot Development Status
# Version 3.0.0

## Current Version Features

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
  restarts without API refetch. Enables fresh-from-source summarization
  in v3.1.0 via Gemini 2.5 Flash Lite's 1M-token context window.
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
- **Context Continuity**: Fresh-from-source summarization via Gemini (v3.1.0)
- **Epoch Management**: Rollover for channels exceeding 25K messages (v3.2.0)
- **Cost Optimization**: Batch API + activity tiering (v3.3.0)

---

## Architecture Status

### Current File Structure
```
├── main.py                    # Entry point (minimal)
├── bot.py                     # Core Discord events (v3.0.0)
├── config.py                  # Configuration management (v1.7.0)
├── commands/                  # Modular command system
│   ├── __init__.py
│   ├── history_commands.py
│   ├── prompt_commands.py
│   ├── ai_provider_commands.py
│   ├── auto_respond_commands.py
│   ├── thinking_commands.py       # v2.1.0
│   └── status_commands.py
├── ai_providers/              # AI provider implementations
│   ├── __init__.py                # Provider factory (v1.3.0)
│   ├── base.py
│   ├── openai_provider.py         # v1.3.0
│   ├── anthropic_provider.py      # v1.1.0
│   └── openai_compatible_provider.py  # v1.2.0
└── utils/                     # Utility modules
    ├── models.py                  # v1.0.0 (NEW — StoredMessage dataclass)
    ├── message_store.py           # v1.0.0 (NEW — SQLite persistence)
    ├── raw_events.py              # v1.0.2 (NEW — message capture + backfill)
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
        ├── realtime_settings_parser.py
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

### 1. v3.1.0 — Gemini Summarization Integration (NEXT)
**Status**: Design phase — depends on v3.0.0 persistence layer
**Design**: Fresh-from-source summarization using Gemini 2.5 Flash Lite

### Resolved Issues
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
