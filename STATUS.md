# STATUS.md
# Discord Bot Development Status
# Version 3.5.2

## Current Version Features

### Version 3.5.2 - Overview Inflation Fix (DEPLOYED)
- **MODIFIED**: `utils/summary_prompts_authoring.py` v1.5.0 — SECRETARY_SYSTEM_PROMPT
  OVERVIEW section now instructs the Secretary to preserve the existing overview
  unless the conversation's purpose has fundamentally changed. Prevents progressive
  overview inflation on incremental updates.
- **TESTED**: Deployed and validated on #openclaw channel. Overview updates only
  when content genuinely changes (e.g., rate limit changed 1000 → 5000 ipm).

### Version 3.5.1 - Pipeline Unification + Classifier Dedup (TESTED)
- **MODIFIED**: `utils/summarizer.py` v2.1.0 — `_incremental_loop()` delegates
  to `incremental_pipeline()` instead of single-pass raw-to-JSON. Both cold
  start and incremental now use the three-pass pipeline.
- **MODIFIED**: `utils/summarizer_authoring.py` v1.9.0 — shared `_run_pipeline()`
  for both paths; `incremental_pipeline()` entry point; `classify_ops()` receives
  `existing_summary` for dedup; Secretary max_tokens scaled with existing minutes.
- **MODIFIED**: `utils/summary_classifier.py` v1.3.0 — `classify_ops()` accepts
  `existing_summary`; `_build_existing_items()` extracts items from stored summary;
  prompt includes EXISTING ITEMS section for semantic dedup.
- **MODIFIED**: `utils/summary_prompts.py` v1.6.0 — camelCase ops in incremental
  prompt to match anyOf STRUCTURER_SCHEMA.
- **TESTED**: Classifier dedup validated on #openclaw channel:
  - Cold start: 539 msgs → 22 ops → 1,180 tokens
  - Incremental (4 new msgs): 16 ops emitted, classifier dropped 9 duplicates,
    kept 7 (3 new items + overview + 2 participants + 1 re-emitted action item)
  - Final: 543 msgs → 2,097 tokens (growth from overview rewrite + 3 new items,
    not from duplication)
  - Classifier correctly identified all 9 semantically duplicate items

### Version 3.5.0 - Discriminated Union Schema (SOW v3.5.0)
- **NEW**: `utils/summary_delta_schema.py` v1.0.0 — anyOf discriminated union
  schema with camelCase enums, propertyOrdering, per-variant required fields.
  Fixes Gemini's constrained decoder skipping add_topic ops.
- **MODIFIED**: `utils/summarizer_authoring.py` v1.6.0 — uses STRUCTURER_SCHEMA,
  calls translate_ops() to map camelCase back to snake_case
- **MODIFIED**: `utils/summary_prompts_authoring.py` v1.4.0 — camelCase op
  names in Structurer prompt
- **MODIFIED**: `ai_providers/gemini_provider.py` v1.2.1 — use_json_schema
  kwarg for anyOf support via response_json_schema config key
- **MODIFIED**: `utils/summary_classifier.py` v1.2.0 — protect topics with
  decisions and action items with owners from being dropped
- **RESULT**: Structurer now produces add_topic ops (4 active, 7 archived).
  Summary: 1,085 tokens with complete topic coverage.

### Version 3.4.0 - M3 Context Integration + KEY FACTS
- M3 context injection: summary appended to system prompt
- KEY FACTS section in Secretary prompt for personal details
- GPT-5.4 nano classifier as quality control pass
- Diagnostic file output for each pipeline stage
- Scaled max_output_tokens to prevent Gemini repetition loop

### Version 3.3.0-3.3.2 - Two-Pass Summarization + Noise Filtering
- Secretary/Structurer two-pass architecture
- ℹ️/⚙️ prefix noise filtering system
- Debug commands, supersession fix, readable snapshots
- Result: 18,619 → 1,871 tokens. 214 → ~15 items.

### Version 3.2.0 - Structured Summary Generation (M2)
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
├── .env
├── data/
│   ├── messages.db                # SQLite + WAL
│   ├── secretary_raw_*.txt        # Secretary diagnostic output
│   ├── structurer_raw_*.json      # Structurer diagnostic output
│   └── classifier_raw_*.json      # Classifier diagnostic output
├── schema/
│   ├── 001.sql                    # v3.0.0 baseline
│   ├── 002.sql                    # v3.1.0 columns + tables
│   └── 003.sql                    # v3.2.3 is_bot_author
├── ai_providers/
│   ├── __init__.py                # v1.4.0
│   ├── openai_provider.py         # v1.3.0
│   ├── anthropic_provider.py      # v1.1.0
│   ├── openai_compatible_provider.py  # v1.2.0
│   └── gemini_provider.py         # v1.2.1
├── commands/
│   ├── __init__.py                # v2.4.0
│   ├── auto_respond_commands.py   # v2.1.0
│   ├── ai_provider_commands.py    # v2.1.0
│   ├── thinking_commands.py       # v2.2.0
│   ├── prompt_commands.py         # v2.1.0
│   ├── status_commands.py         # v2.1.0
│   ├── history_commands.py        # v2.1.0
│   ├── summary_commands.py        # v2.2.0
│   └── debug_commands.py          # v1.1.0
├── utils/
│   ├── models.py                  # v1.2.0
│   ├── message_store.py           # v1.2.0
│   ├── raw_events.py              # v1.2.0
│   ├── db_migration.py            # v1.0.0
│   ├── context_manager.py         # v1.1.0
│   ├── response_handler.py        # v1.1.4
│   ├── summarizer.py              # v2.1.0
│   ├── summarizer_authoring.py    # v1.9.0
│   ├── summary_schema.py          # v1.4.0
│   ├── summary_delta_schema.py    # v1.0.0
│   ├── summary_classifier.py      # v1.3.0
│   ├── summary_store.py           # v1.1.0
│   ├── summary_prompts.py         # v1.6.0
│   ├── summary_prompts_authoring.py  # v1.5.0
│   ├── summary_display.py         # v1.2.1
│   ├── summary_normalization.py   # v1.0.1
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
1. **250-line file limit** — mandatory for all files
2. **Single responsibility** — each module serves one clear purpose
3. **Comprehensive documentation** — detailed docstrings and inline comments
4. **Module-specific logging** — structured logging with appropriate levels
5. **Error handling** — graceful degradation and proper error recovery
6. **Version tracking** — proper version numbers and changelogs in all files
7. **Async safety** — all provider API calls wrapped in run_in_executor()
8. **Provider efficiency** — singleton caching prevents unnecessary instantiation
9. **Token safety** — every API call budget-checked against provider context window
10. **Message persistence** — all messages stored in SQLite via on_message listener

---

## Resolved Issues
- ✅ Overview inflation on incremental updates — resolved in v3.5.2 (Secretary guidance)
- ✅ Incremental path uses old schema — resolved in v3.5.1 (unified pipeline)
- ✅ Classifier dedup against existing items — tested in v3.5.1
- ✅ Structurer skipping topics — resolved in v3.5.0 (anyOf schema)
- ✅ M3 context integration — resolved in v3.4.0
- ✅ Summarization quality — resolved in v3.3.0 (Secretary architecture)
- ✅ Decision supersession — resolved in v3.3.1
- ✅ Summary output contamination — resolved in v3.3.0 (prefix system)
- ✅ Bot message noise in summaries — resolved in v3.2.3
- ✅ Message persistence — resolved in v3.0.0
- ✅ Token-based context trimming — resolved in v2.23.0

## Current Priority Issues

### 1. config.py Default SUMMARIZER_MODEL
Default `gemini-2.5-flash-lite` is stale. Server runs
`gemini-3.1-flash-lite-preview` via .env override. Consider updating.

### 2. Merge claude-code → development
Feature branch has accumulated v3.3.0 through v3.5.2. Ready for merge.
