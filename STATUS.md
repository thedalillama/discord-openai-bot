# STATUS.md
# Discord Bot Development Status
# Version 5.3.0

## Current Version Features

### Version 5.3.0 — Cross-Cluster Overview + Pipeline Wiring
- **NEW**: `utils/cluster_overview.py` v1.0.0 — `OVERVIEW_SYSTEM_PROMPT`,
  `OVERVIEW_SCHEMA` (flat JSON, participants field); `_format_cluster_input()`
  formats stored cluster summaries as text; `generate_overview()` single Gemini
  call → channel-level overview; `translate_to_channel_summary()` maps v5.2.0
  `text` fields to v4.x field names (`fact`/`task`/`question`/`decision`) so
  `format_always_on_context()` requires zero changes; `run_cluster_pipeline()`
  full pipeline orchestrator (cluster → summarize → overview → save)
- **MODIFIED**: `utils/summarizer.py` v3.0.0 — `summarize_channel()` routes to
  `run_cluster_pipeline()`; v4.x functions retained for rollback safety
- **MODIFIED**: `commands/summary_commands.py` v2.3.0 — `!summary create`
  displays cluster-v5 stats; `!summary clear` also calls `clear_channel_clusters()`

### Version 5.2.0 — Per-Cluster LLM Summarization
- **NEW**: `utils/cluster_summarizer.py` v1.0.0 — per-cluster Gemini summarization;
  `CLUSTER_SYSTEM_PROMPT` and `CLUSTER_SUMMARY_SCHEMA` (flat JSON, summary field first);
  `summarize_cluster()` loads messages, formats with M-labels (truncates to 50 most
  recent), calls Gemini with structured output, stores label/summary/status;
  `summarize_all_clusters()` sequential loop with retry-on-failure
- **MODIFIED**: `utils/cluster_store.py` v1.1.0 — added `get_cluster_message_ids()`,
  `get_clusters_for_channel()`, `update_cluster_label_summary()`, `get_messages_by_ids()`
  (placed here instead of message_store.py which is at 254 lines)
- **MODIFIED**: `commands/debug_commands.py` v1.5.0 — added `!debug summarize_clusters`;
  iterates all clusters, calls `summarize_cluster()` per cluster, sends Discord progress
  every 5 clusters, paginates final report

### Version 5.1.0 — Schema + HDBSCAN Clustering Core
- **NEW**: `schema/005.sql` — `clusters` and `cluster_messages` tables;
  `clusters.embedding` stores cluster centroid as packed BLOB
- **NEW**: `utils/cluster_engine.py` v1.0.0 — UMAP (1536→5 dims) +
  HDBSCAN clustering pipeline; noise reassignment via cosine similarity to
  centroids; centroids computed in original 1536-dim space
- **NEW**: `utils/cluster_store.py` v1.0.0 — CRUD (store_cluster,
  clear_channel_clusters, get_cluster_stats), orchestrator (run_clustering),
  Discord formatter (format_cluster_report)
- **MODIFIED**: `config.py` v1.13.0 — add CLUSTER_MIN_CLUSTER_SIZE (5),
  CLUSTER_MIN_SAMPLES (3), UMAP_N_NEIGHBORS (15), UMAP_N_COMPONENTS (5)
- **MODIFIED**: `commands/debug_commands.py` v1.4.1 — add `!debug clusters`
  diagnostic command (v1.4.0) + paginate output (v1.4.1)
- **MODIFIED**: `requirements.txt` — add scikit-learn>=1.3, umap-learn>=0.5

### Version 4.1.10 - Inject Today's Date into Context
- **MODIFIED**: `utils/context_manager.py` v2.1.5 — `Today's date: YYYY-MM-DD`
  injected at top of CONVERSATION CONTEXT block in both the retrieved and
  full-summary fallback paths; model can now interpret retrieved message
  timestamps relative to the current date

### Version 4.1.9 - Timestamps on Retrieved Messages
- **MODIFIED**: `utils/embedding_store.py` v1.7.0 — `find_similar_messages()`
  now returns `created_at` as 4th element instead of score; score used
  internally for sort only
- **MODIFIED**: `utils/context_manager.py` v2.1.4 — `_retrieve_topic_context()`
  and `_fallback_msg_search()` prepend `[YYYY-MM-DD]` to each retrieved message
  line so the model can distinguish old from recent discussions

### Version 4.1.8 - Batched Cold Start
- **MODIFIED**: `utils/summarizer.py` v2.2.0 — cold start now slices to
  `effective_batch` before calling `cold_start_pipeline()`; remaining messages
  continue through `_incremental_loop()`; prevents 65K+ token Structurer
  responses on large initial ingest

### Version 4.1.7 - Batch Embedding Backfill
- **MODIFIED**: `utils/embedding_store.py` v1.6.0 — added `embed_texts_batch()`;
  calls OpenAI embeddings API in batches of 1000 texts per request; per-batch
  failures logged and skipped; returns (index, vector) pairs for successes
- **MODIFIED**: `commands/debug_commands.py` v1.3.0 — `!debug backfill` now
  collects all pending message texts, calls `embed_texts_batch()` in 1000-message
  batches, logs per-batch progress and total elapsed time; also fixes re-link to
  include archived_topics (was active_topics only)

### Version 4.1.6 - Restore Always-On Context Injection
- **MODIFIED**: `utils/context_manager.py` v2.1.3 — always-on block (overview,
  key facts, open actions, open questions) restored alongside retrieved content;
  covers personal/project facts not reachable via topic retrieval

### Version 4.1.5 - Full Summary Fallback as Warning (Branch 4)
- **MODIFIED**: `utils/context_manager.py` v2.1.2 — branch 4 (no topics + no
  message embeddings) now logs WARNING instead of DEBUG; degraded retrieval
  state is visible in monitoring without behavior change

### Version 4.1.4 - Secretary Prompt: Ignore Bot Noise (Fix 1B)
- **MODIFIED**: `utils/summary_prompts_authoring.py` v1.6.0 — added IGNORE section
  to `SECRETARY_SYSTEM_PROMPT`; instructs Secretary to omit bot self-descriptions,
  capability statements, diagnostic responses, and conversational filler from
  minutes; prevents bot-noise topics from being created at summarization time

### Version 4.1.3 - Noise Topic Filter at Retrieval Time (Fix 1A)
- **MODIFIED**: `utils/embedding_store.py` v1.5.0 — added `_is_noise_topic()` and
  `_NOISE_PATTERNS`; `find_relevant_topics()` skips bot-noise topics before scoring
  so they cannot consume retrieval budget; filtered topics logged at DEBUG

### Version 4.1.2 - Topic Deduplication (Fix 2A)
- **MODIFIED**: `utils/embedding_store.py` v1.4.0 — added `clear_channel_topics()`;
  deletes all topics + topic_messages for a channel before inserting fresh set
- **MODIFIED**: `utils/summarizer_authoring.py` v1.10.2 — calls `clear_channel_topics()`
  before topic storage loop; each `!summary create` now produces the authoritative
  topic set with no duplicates accumulating across runs

### Version 4.1.1 - Key Facts Framing Fix
- **MODIFIED**: `utils/summary_display.py` v1.3.1 — changed "Key facts:" label to
  "Key facts established in this conversation:" so the model treats them as discussed
  content rather than background knowledge; fixes false "we haven't discussed X" replies
  when X is present in key facts but not in retrieved topic messages

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
│   ├── 004.sql                    # v4.0.0 topics, topic_messages, message_embeddings
│   └── 005.sql                    # v5.1.0 clusters, cluster_messages
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
│   ├── summary_commands.py        # v2.3.0
│   └── debug_commands.py          # v1.5.0
├── utils/
│   ├── cluster_engine.py          # v1.0.0
│   ├── cluster_store.py           # v1.1.0
│   ├── cluster_overview.py        # v1.0.0
│   ├── cluster_summarizer.py      # v1.0.0
│   ├── logging_utils.py           # v1.1.0
│   ├── models.py                  # v1.2.0
│   ├── message_store.py           # v1.2.0
│   ├── raw_events.py              # v1.3.0
│   ├── db_migration.py            # v1.0.0
│   ├── embedding_store.py         # v1.5.0
│   ├── context_manager.py         # v2.1.3
│   ├── response_handler.py        # v1.1.4
│   ├── summarizer.py              # v3.0.0
│   ├── summarizer_authoring.py    # v1.10.2
│   ├── summary_schema.py          # v1.4.0
│   ├── summary_delta_schema.py    # v1.0.0
│   ├── summary_classifier.py      # v1.3.0
│   ├── summary_store.py           # v1.1.0
│   ├── summary_prompts.py         # v1.6.0
│   ├── summary_prompts_authoring.py  # v1.6.0
│   ├── summary_display.py         # v1.3.1
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
