# STATUS.md
# Discord Bot Development Status
# Version 5.10.1

## Current Version Features

### Version 5.10.1 — Dead Code Removal (Imports + Dev Helpers)

Removed 11 unused imports across 7 files, 3 unused functions, and the
`utils/history/diagnostics.py` dev-helper module (4 functions with no active
callers since extraction in v2.x). All removals are import-clean — git history
preserves all deleted code.

**Removed imports:**
- `bot.py`: `defaultdict`, `DEFAULT_SYSTEM_PROMPT`, `is_bot_command`, `channel_locks`
- `ai_providers/__init__.py`: `AIProvider` (base class, not referenced at module level)
- `ai_providers/openai_provider.py`: `io` (BytesIO only needed in response_handler)
- `commands/auto_respond_commands.py`: `DEFAULT_AUTO_RESPOND`
- `commands/cluster_commands.py`: `json`
- `commands/prompt_commands.py`: `channel_history`, `DEFAULT_SYSTEM_PROMPT`
- `utils/models.py`: `field` from dataclasses

**Removed functions:**
- `utils/response_handler.py`: `send_text_response()`, `send_image_response()` — image/text sending is done inline in `handle_ai_response_task()`
- `ai_providers/__init__.py`: `clear_provider_cache()` — no callers in active codebase

**Deleted file:**
- `utils/history/diagnostics.py` v1.0.0 — 4 dev diagnostic helpers (`get_channel_diagnostics`, `identify_potential_issues`, `estimate_memory_usage`, `analyze_channel_health`) with no command callers since extraction in v2.x. Removed import chain from `__init__.py`, `loading_utils.py`, `loading.py`.

---

### Version 5.10.0 — Dead Code Removal (v4.x Pipeline)

Removed 10 files comprising the v4.x three-pass summarization pipeline and
topic-based retrieval system. These were retained for rollback safety during
v5 development but have had zero active callers since v5.3.0 (summarization)
and v5.5.0 (retrieval). Git history preserves all deleted code.

**Deleted files:**
- `utils/summarizer_authoring.py` v1.10.2 — Three-pass Secretary/Structurer/Classifier
- `utils/summary_delta_schema.py` v1.0.0 — anyOf discriminated union schema
- `utils/summary_classifier.py` v1.3.0 — Old GPT-4o-mini KEEP/DROP/RECLASSIFY
- `utils/summary_prompts_authoring.py` v1.7.0 — Secretary prompt construction
- `utils/summary_prompts_structurer.py` v1.0.0 — Structurer prompt construction
- `utils/summary_prompts.py` v1.6.0 — Label map builder
- `utils/summary_schema.py` v1.4.0 — Delta ops, hash verification
- `utils/summary_normalization.py` v1.0.1 — Layer 2 response normalization
- `utils/summary_validation.py` v1.1.0 — Layer 3 domain validation
- `utils/topic_store.py` v1.0.0 — Topic CRUD + message linking

**Modified files:**
- `utils/summarizer.py` v4.0.0 — removed 5 dead functions; now a 69-line router
- `commands/cluster_commands.py` v1.2.0 — removed vestigial topic re-link from backfill

---

### Version 5.9.1 — Citation Tuning + Partial Cluster Injection

- Citation instruction moved to context block with concrete example
- Partial cluster injection — messages injected one by one until budget hit
- `CONTEXT_BUDGET_PERCENT` raised 15→80 in `.env`
- Citation behavior: Anthropic (Claude) reliable; DeepSeek/gpt-4o-mini ignore

### Version 5.9.0 — Citation-Backed Responses

Retrieved messages labeled `[N]` in context; LLM cites inline; hallucinated
citations stripped; Sources footer appended (≤1950 chars inline, else ℹ️ follow-up).

### Post-5.9.1 Fixes

- `raw_events.py` v1.7.0: `!help` output filtered from embedding
- `debug_commands.py`: `!help` description added to debug group
- `context_manager.py` v2.5.1: debug prompt dump to `/tmp/last_system_prompt.txt`

---

## Project File Tree

```
discord-bot/
├── bot.py                         # v3.3.0
├── config.py                      # v1.12.6
├── main.py
├── .env
├── data/
│   └── messages.db                # SQLite + WAL
├── schema/
│   ├── 001.sql                    # v3.0.0 baseline
│   ├── 002.sql                    # v3.1.0 columns + tables
│   ├── 003.sql                    # v3.2.3 is_bot_author
│   ├── 004.sql                    # v4.0.0 topics, topic_messages, message_embeddings
│   ├── 005.sql                    # v5.1.0 clusters, cluster_messages
│   └── 006.sql                    # v5.4.0 needs_resummarize column
├── ai_providers/
│   ├── __init__.py                # v1.5.0
│   ├── openai_provider.py         # v1.4.0
│   ├── anthropic_provider.py      # v1.1.0
│   ├── openai_compatible_provider.py  # v1.2.0
│   └── gemini_provider.py         # v1.2.1
├── commands/
│   ├── __init__.py                # v2.7.0
│   ├── summary_commands.py        # v2.4.0
│   ├── debug_commands.py          # v1.8.0
│   ├── cluster_commands.py        # v1.3.0
│   ├── dedup_commands.py          # v1.0.0
│   ├── explain_commands.py        # v1.1.0
│   ├── auto_respond_commands.py   # v2.2.0
│   ├── ai_provider_commands.py    # v2.1.0
│   ├── thinking_commands.py       # v2.2.0
│   ├── prompt_commands.py         # v2.2.0
│   ├── status_commands.py         # v2.1.0
│   └── history_commands.py        # v2.1.0
├── utils/
│   ├── citation_utils.py          # v1.0.0
│   ├── receipt_store.py           # v1.0.0
│   ├── cluster_engine.py          # v1.0.1
│   ├── cluster_store.py           # v2.0.0
│   ├── cluster_summarizer.py      # v1.0.0
│   ├── cluster_overview.py        # v2.2.0
│   ├── cluster_classifier.py      # v1.6.0
│   ├── cluster_qa.py              # v1.0.0
│   ├── cluster_assign.py          # v1.0.0
│   ├── cluster_update.py          # v1.0.0
│   ├── cluster_retrieval.py       # v1.0.0
│   ├── logging_utils.py           # v1.1.0
│   ├── models.py                  # v1.3.0
│   ├── message_store.py           # v1.2.0
│   ├── raw_events.py              # v1.7.0
│   ├── db_migration.py            # v1.0.0
│   ├── embedding_store.py         # v1.9.0
│   ├── embedding_context.py       # v1.4.0
│   ├── context_retrieval.py       # v1.4.0
│   ├── context_manager.py         # v2.5.1
│   ├── response_handler.py        # v1.4.0
│   ├── summarizer.py              # v4.0.0
│   ├── summary_store.py           # v1.1.0
│   ├── summary_display.py         # v1.3.2
│   └── history/
│       ├── message_processing.py  # v2.3.0
│       ├── realtime_settings_parser.py  # v2.2.0
│       └── ...
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

## Known Limitations / Next Priorities

### 1. Citation — Model-Dependent (v5.9.x)
Citations work reliably with Anthropic (Claude) but DeepSeek Reasoner and
gpt-4o-mini consistently ignore `[N]` citation instructions. A prefill/few-shot
approach or post-hoc citation matching by string similarity may help.

### 2. Hierarchical Semantic Memory
Channel summaries are flat and per-channel. No cross-channel memory, no
user-level memory, no long-term summarization surviving `!summary create` wipe.

### 3. Context-Prepending Evaluation (v5.8.0)
Topic-boundary cosine similarity filtering `CONTEXT_SIMILARITY_THRESHOLD=0.3`
was set heuristically and has not been systematically evaluated.

### 4. Legacy Cluster Noise
Command outputs that slipped through before v5.5.1/v1.7.0 may still be in
existing clusters. A `!summary create` in affected channels will re-cluster
from current embeddings, removing the noise.

---

For detailed version history prior to v5.9.0, see git log.
