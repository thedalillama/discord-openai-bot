# STATUS.md
# Discord Bot Development Status
# Version 3.5.0

## Current Version Features

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
│   ├── summarizer.py              # v1.9.0
│   ├── summarizer_authoring.py    # v1.6.0
│   ├── summary_schema.py          # v1.4.0
│   ├── summary_delta_schema.py    # v1.0.0
│   ├── summary_classifier.py      # v1.2.0
│   ├── summary_store.py           # v1.1.0
│   ├── summary_prompts.py         # v1.5.0
│   ├── summary_prompts_authoring.py  # v1.4.0
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

## Resolved Issues
- ✅ Structurer skipping topics — resolved in v3.5.0 (anyOf schema)
- ✅ M3 context integration — resolved in v3.4.0
- ✅ Summarization quality — resolved in v3.3.0 (Secretary architecture)
- ✅ Decision supersession — resolved in v3.3.1
- ✅ Summary output contamination — resolved in v3.3.0 (prefix system)
- ✅ Bot message noise in summaries — resolved in v3.2.3
- ✅ Message persistence — resolved in v3.0.0
- ✅ Token-based context trimming — resolved in v2.23.0

## Current Priority Issues

### 1. Incremental Path Uses Old Schema
The incremental update path in `summarizer.py` still uses the flat
DELTA_SCHEMA. Should be migrated to the anyOf STRUCTURER_SCHEMA.

### 2. Classifier Tuning
Classifier occasionally drops items incorrectly. Rules added in v1.2.0
but may need further refinement with more test data.

### 3. Merge claude-code → development
Feature branch has accumulated v3.3.0 through v3.5.0. Ready for merge.
