# STATUS.md
# Discord Bot Development Status
# Version 3.4.0

## Current Version Features

### Version 3.4.0 - M3 Context Integration + KEY FACTS
- **MODIFIED**: `utils/context_manager.py` v1.1.0 — `build_context_for_provider()`
  loads channel summary and appends it to the system prompt. Bot now has
  conversational memory of decisions, topics, facts, and action items.
- **MODIFIED**: `utils/summary_display.py` v1.2.1 — `format_summary_for_context()`
  formats full summary as plain text for system prompt injection. Key Facts
  moved from full-only to default `!summary` view.
- **MODIFIED**: `utils/summary_prompts_authoring.py` v1.2.0 — KEY FACTS section
  added to Secretary prompt with GOOD/BAD examples for personal details.
  Structurer updated with `add_fact` extraction rule.
- **ADDED**: `test_pipeline.py` — standalone script runs Secretary + Structurer
  pipeline outside Discord, shows both outputs
- **ADDED**: `test_summary.py` — inspect stored summary + interactive Q&A
- **MODIFIED**: `README_ENV.md` v3.4.0 — added Gemini/summarizer variables
- **TESTED**: Bot recalls decisions, personal facts (favorite number 333,
  age 65, lives in NJ), action items from 400+ messages ago via summary memory

### Version 3.3.2 - Debug Command Group
- **ADDED**: `commands/debug_commands.py` v1.0.0 — `!debug noise/cleanup/status`
- **MODIFIED**: `commands/__init__.py` v2.4.0 — registers debug_commands
- **REMOVED**: `commands/cleanup_commands.py`

### Version 3.3.1 - Supersession Fix + Readable Snapshots
- **MODIFIED**: `utils/summary_schema.py` v1.4.0 — `_supersede()` always retires
  old decision even with empty text
- **MODIFIED**: `utils/summary_prompts.py` v1.5.0 — readable text in snapshots
- **MODIFIED**: `utils/summary_prompts_authoring.py` v1.1.2 — M-labels skipped

### Version 3.3.0 - Two-Pass Summarization + Prefix Noise Filtering
- **ADDED**: `utils/summary_prompts_authoring.py` v1.1.1 — Secretary/Structurer
- **ADDED**: `utils/summarizer_authoring.py` v1.0.1 — cold start pipeline
- **ADDED**: `utils/summary_display.py` v1.1.0 — paginated display
- **MODIFIED**: All command modules — ℹ️/⚙️ prefix system
- **MODIFIED**: `utils/history/message_processing.py` v2.3.0 — prefix filters
- **RESULT**: 18,619 → 1,871 tokens. 214 → ~15 meaningful items.

### Version 3.2.3 - Summary Quality & Bot Message Filtering
### Version 3.2.2 - Three-Layer Enforcement Architecture
### Version 3.2.0 - Structured Summary Generation (M2)
### Version 3.1.1 - Code Quality: realtime_settings_parser.py split
### Version 3.1.0 - Schema Extension & Enhanced Capture
### Version 3.0.0 - SQLite Message Persistence Layer
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
├── config.py                      # v1.11.0
├── main.py
├── test_pipeline.py               # Summarization pipeline inspector
├── test_summary.py                # Summary + interactive Q&A inspector
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
│   ├── context_manager.py         # v1.1.0
│   ├── response_handler.py        # v1.1.4
│   ├── summarizer.py              # v1.9.0
│   ├── summarizer_authoring.py    # v1.0.1
│   ├── summary_schema.py          # v1.4.0
│   ├── summary_store.py           # v1.1.0
│   ├── summary_prompts.py         # v1.5.0
│   ├── summary_prompts_authoring.py  # v1.2.0
│   ├── summary_display.py         # v1.2.1
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
- ✅ M3 context integration — resolved in v3.4.0
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

### 1. Archived Items Bloating Summary
Secretary produces 50+ archived one-liners; Structurer converts each to
a separate topic. Need to condense ARCHIVED to 5-6 category-level entries.

### 2. Topic-Centric Schema Redesign (Future)
Items (decisions, facts, actions) should nest under parent topics with
snowflake message IDs as immutable evidence anchors. Design discussed,
implementation deferred.

### 3. config.py Default SUMMARIZER_MODEL
Default is `gemini-2.5-flash-lite` but deployed server uses
`gemini-3.1-flash-lite-preview` via .env override. Consider updating default.

### 4. WAL File Stats Bug
`get_database_stats()` reports 0.0 MB — only measures main file, not WAL.
