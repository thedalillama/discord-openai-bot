# STATUS.md
# Discord Bot Development Status
# Version 4.1.0

## Current Version Features

### Version 4.1.0 - Direct Message Embedding Fallback (SOW v4.1.0)
- **MODIFIED**: `utils/embedding_store.py` v1.3.0 — added `find_similar_messages()`;
  searches message_embeddings directly by cosine similarity for fallback retrieval
- **MODIFIED**: `utils/context_manager.py` v2.1.0 — added `_fallback_msg_search()`;
  fires at both failure points in `_retrieve_topic_context()` (no topics above
  threshold, and topics found but all had 0 linked messages)
- **MODIFIED**: `config.py` v1.12.6 — added RETRIEVAL_MSG_FALLBACK (default 15)

### Version 4.0.0 - Topic-Based Semantic Retrieval (DEPLOYED + TESTED)
- **NEW**: `utils/embedding_store.py` v1.2.0 — OpenAI text-embedding-3-small,
  cosine similarity, threshold-based topic-message linkage
- **NEW**: `schema/004.sql` — topics, topic_messages, message_embeddings tables
- **MODIFIED**: `utils/raw_events.py` v1.3.0 — embed messages on arrival
- **MODIFIED**: `utils/summarizer_authoring.py` v1.10.1 — store active + archived topics
- **MODIFIED**: `utils/summary_display.py` v1.3.0 — format_always_on_context()
- **MODIFIED**: `utils/context_manager.py` v2.0.4 — always-on + semantic retrieval
- **MODIFIED**: `config.py` v1.12.5 — EMBEDDING_MODEL, RETRIEVAL_TOP_K,
  RETRIEVAL_MIN_SCORE (0.3), TOPIC_LINK_MIN_SCORE (0.3), MAX_RECENT_MESSAGES (5)
- **MODIFIED**: `commands/debug_commands.py` v1.2.0 — !debug backfill command
- **TESTED**: Retrieval validated on #openclaw:
  - "what have we said about gorillas?" — retrieved strength + diet + bachelor party toast
  - "how are we related to them?" — retrieved common ancestor / DNA similarity
  - "who else did we say humans are closely related to?" — retrieved bonobos/chimps
  - Similarity threshold (0.3) filters unrelated topics (aerodynamics, etc.)

### Version 3.5.2 - Overview Inflation Fix (DEPLOYED)
- **MODIFIED**: `utils/summary_prompts_authoring.py` v1.5.0 — Secretary preserves
  existing overview unless conversation purpose fundamentally changes.

### Version 3.5.1 - Pipeline Unification + Classifier Dedup (TESTED)
- **MODIFIED**: `utils/summarizer.py` v2.1.0 — delegates to `incremental_pipeline()`
- **MODIFIED**: `utils/summarizer_authoring.py` v1.9.0 — shared `_run_pipeline()`
- **MODIFIED**: `utils/summary_classifier.py` v1.3.0 — dedup against existing items
- **MODIFIED**: `utils/summary_prompts.py` v1.6.0 — camelCase ops in incremental prompt
- **TESTED**: Cold start 1,180 tokens → incremental 2,097 tokens; classifier dropped 9/9 duplicates

### Version 3.5.0 - Discriminated Union Schema
- **NEW**: `utils/summary_delta_schema.py` v1.0.0 — anyOf schema, camelCase enums
- Result: Structurer now produces add_topic ops (4 active, 7 archived)

### Version 3.4.0 - M3 Context Integration + KEY FACTS
### Version 3.3.0-3.3.2 - Two-Pass Summarization + Noise Filtering
### Version 3.2.0 - Structured Summary Generation (M2)
### Version 3.1.0 - Schema Extension & Enhanced Capture
### Version 3.0.0 - SQLite Message Persistence Layer
### Version 2.23.0 - Token-Budget Context Management + Usage Logging
### Version 2.22.0 - Provider Singleton Caching
### Version 2.21.0 - Async Executor Safety
### Version 2.20.0 - DeepSeek Reasoning Content Display

---

## Project File Tree (current versions)

```
discord-bot/
├── bot.py                         # v3.1.0
├── config.py                      # v1.12.6
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
│   ├── 003.sql                    # v3.2.3 is_bot_author
│   └── 004.sql                    # v4.0.0 topics, topic_messages, message_embeddings
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
│   └── debug_commands.py          # v1.2.0
├── utils/
│   ├── models.py                  # v1.2.0
│   ├── message_store.py           # v1.2.0
│   ├── raw_events.py              # v1.3.0
│   ├── db_migration.py            # v1.0.0
│   ├── embedding_store.py         # v1.3.0
│   ├── context_manager.py         # v2.1.0
│   ├── response_handler.py        # v1.1.4
│   ├── summarizer.py              # v2.1.0
│   ├── summarizer_authoring.py    # v1.10.1
│   ├── summary_schema.py          # v1.4.0
│   ├── summary_delta_schema.py    # v1.0.0
│   ├── summary_classifier.py      # v1.3.0
│   ├── summary_store.py           # v1.1.0
│   ├── summary_prompts.py         # v1.6.0
│   ├── summary_prompts_authoring.py  # v1.5.0
│   ├── summary_display.py         # v1.3.0
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
- ✅ Topic retrieval budget too small (40% slice) — fixed v4.0.0 (full remaining budget)
- ✅ Unrelated topics retrieved — fixed v4.0.0 (RETRIEVAL_MIN_SCORE threshold)
- ✅ Recent messages overwhelming retrieved context — fixed v4.0.0 (MAX_RECENT_MESSAGES=5)
- ✅ Model ignoring retrieved history — fixed v4.0.0 (explicit framing in system prompt)
- ✅ Topic-message count cap (top-20) — fixed v4.0.0 (threshold-based linking)
- ✅ Archived topics not available for retrieval — fixed v4.0.0 (store active+archived)
- ✅ Overview inflation on incremental updates — resolved v3.5.2
- ✅ Incremental path uses old schema — resolved v3.5.1
- ✅ Classifier dedup against existing items — tested v3.5.1
- ✅ Structurer skipping topics — resolved v3.5.0 (anyOf schema)
- ✅ M3 context integration — resolved v3.4.0
- ✅ Summarization quality — resolved v3.3.0 (Secretary architecture)
- ✅ Summary output contamination — resolved v3.3.0 (prefix system)
- ✅ Message persistence — resolved v3.0.0
- ✅ Token-based context trimming — resolved v2.23.0

## Known Limitations / Next Priorities

### 1. Orphaned Messages — partially addressed in v4.1.0
Direct message fallback now surfaces orphaned messages via embedding similarity
when no topics match. However, messages with very low similarity scores (below
RETRIEVAL_MIN_SCORE=0.3) will still be missed. A future topic discovery pass
could cluster orphaned messages into new topics.

### 2. config.py Default SUMMARIZER_MODEL
Default `gemini-2.5-flash-lite` is stale. Server runs
`gemini-3.1-flash-lite-preview` via .env override.

### 3. WAL File Stats Bug
`get_database_stats()` reports 0.0 MB — only measures main file, not WAL.
