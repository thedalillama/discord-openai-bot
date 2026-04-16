# HANDOFF.md
# Discord Bot Development Status
# Version 6.4.2

## Current Version Features

### Version 6.4.2 — Benchmark Score Fix + History Seeding

**Benchmark score-scale fix (`top_score` was RRF; now correctly cosine):**

v6.4.0 introduced `rrf_fuse()` which returns `(seg_id, rrf_score)` pairs.
`retrieval_benchmark.py` iterated those pairs and put `rrf_score` in the
segment score slot — the slot that v6.2.0 used for cosine. Result: reported
"top_score" of 0.04–0.19 vs v6.2.0's 0.4–0.7, making v6.4.0 look like a
severe regression. In reality, retrieval quality improved.

Fix: `run_query()` in `benchmark_core.py` builds explicit 5-tuples
`(sid, topic_label, synthesis, cosine_score, rrf_score)` by looking up each
fused `sid` in `dense_map` (which carries the cosine score from
`find_relevant_segments()`). BM25-only segments (not in dense pool) get
`cosine_score=None` and are excluded from cosine averages.
`score_result()` returns both `top_cosine_score` (primary, 0–1) and
`top_rrf_score` (secondary, ~0–0.19). JSON output includes `score_note`
documenting the historical confusion.

**v6.4.2 benchmark baseline (2026-04-16):**
- Avg top cosine: 0.391, 16/16 queries have cosine
- Avg keyword recall: 60%, 0 empty retrievals, 2328ms avg latency
- File: `benchmarks/benchmark_v6.4.2_2026-04-16T05-53-47.json`

**History seeding fix (`_seed_history_from_db`):**

After restart with 0 delta messages, `channel_history` was empty → bot replied
"No conversation history available." Root cause: `load_messages_from_discord`
returned without seeding any in-memory history.

Fix in `discord_loader.py` v2.3.0: `_seed_history_from_db(channel_id)` queries
`get_channel_messages(channel_id)`, takes the last `MAX_HISTORY * 10` records
(500), filters noise/commands/ℹ️ bot output, then seeds the last `MAX_HISTORY`
(50) valid entries via `add_message_to_history()`. The `× 10` window is needed
because most DB records in bot-heavy channels are `ℹ️`-prefixed and would
exhaust the window before yielding 50 real conversation messages.

**`!history` overflow fix:**
`history_commands.py` v2.2.0: `content` truncated to 350 chars before building
the entry string. Previous pagination checked chunk size but not individual
entry size — a single long bot response could produce a >2000-char `ctx.send()`.

**Files changed:**
- `utils/history/discord_loader.py` v2.2.0 → v2.3.0 (`_seed_history_from_db`)
- `commands/history_commands.py` v2.1.0 → v2.2.0 (350-char content truncation)
- `retrieval_benchmark.py` v2.0.0 (main entry point only; split to 3 files)
- `benchmark_queries.py` v1.0.0 (new — `BENCHMARK_QUERIES` extracted)
- `benchmark_core.py` v1.0.0 (new — `get_all_channel_ids`, `get_cluster_count`,
  `run_query`, `score_result`)
- `cluster_diagnostic.py` deleted (pre-v6 cluster quality tool, `cluster_messages`
  never populated in v6 pipeline)

---

### Version 6.4.1 — Startup Fetch Optimization

Eliminates the full Discord channel history fetch on startup. Settings are now
restored from SQLite; Discord is only queried for the delta since the last
DB-recorded message.

**Files changed:**
- `utils/history/realtime_settings_parser.py` v2.3.0 — `restore_settings_from_db(channel_id)`:
  queries `messages WHERE is_bot_author=1 AND content LIKE '⚙️%' ORDER BY DESC LIMIT 200`,
  wraps rows as `_Msg` duck-typed objects, calls existing `parse_settings_during_load()`
- `utils/history/discord_fetcher.py` v1.3.0 — `after_id=None` param: when set, uses
  `channel.history(after=discord.Object(id=after_id), oldest_first=True)`, returning
  `(messages, 0)` without skip logic
- `utils/history/discord_loader.py` v2.2.0 — calls `restore_settings_from_db()` first,
  then `get_last_processed_id()`, passes `after_id=last_id` to fetcher; still parses any
  fresh delta messages for settings

**Also in v6.4.x:** thread-local SQLite, backfill error logging, segment-count logging,
dropped-message logging, proposition embedding retry, pipeline label in footer/meta.

---

### Version 6.4.0 — Proposition Decomposition (SOW v6.3.0)

Three-signal hybrid retrieval: proposition embeddings added as a third RRF
signal alongside dense segment embeddings and BM25.

**Retrieval flow (`_retrieve_segment_context` in `context_retrieval.py`):**
1. Embed query via `embed_query_with_smart_context()` (unchanged)
2. `find_relevant_propositions()` — cosine vs all prop embeddings; collapse
   to max-score-per-segment → segment IDs (no size bias)
3. `find_relevant_segments(top_k * 2)` — cosine vs segment embeddings → IDs
4. `_apply_score_gap()` — prune dense candidates
5. `fts_search()` — BM25 via FTS5 → segment IDs
6. `rrf_fuse(prop, dense, bm25, k=RRF_K)` — rank fusion → top-K IDs
7. `get_segment_with_messages()` → synthesis + source messages injected

**Pipeline addition (`summarizer.py`):**
After `populate_fts()`, before `run_segment_clustering()`:
```python
prop_count = await run_proposition_phase(channel_id, progress_fn)
```
`run_proposition_phase()` in `proposition_decomposer.py`:
1. Load segment syntheses from DB
2. Batch-decompose via GPT-4o-mini (PROPOSITION_BATCH_SIZE=10 per call)
3. Store in `propositions` table
4. Embed each proposition via OpenAI
5. Store embeddings

**Failure modes:** proposition phase logs warning and continues; retrieval
degrades to dense+BM25 (v6.2.0 behavior). Rollback is single-line removal
of `prop_ranked` from `rrf_fuse()` call in `context_retrieval.py`.

**New config:** `PROPOSITION_BATCH_SIZE=10`, `PROPOSITION_PROVIDER=openai`
**New files:** `utils/proposition_store.py` v1.0.0,
`utils/proposition_decomposer.py` v1.0.0, `schema/010.sql`
**Modified:** `cluster_retrieval.py` v1.3.0, `context_retrieval.py` v1.8.0,
`fts_search.py` v1.1.0, `summarizer.py` v4.3.0, `config.py` v1.19.0,
`cluster_commands.py` v1.6.0

---

### Version 6.3.0 — Dead Command Removal + Doc Accuracy

Removed three obsolete commands and fixed stale descriptions/labels throughout.

**Removed:**
- `!summary raw` — `minutes_text` never populated by v5.x+ pipeline (Secretary removed v5.10.0)
- `!debug clusters` — ran v5.x message-embedding clustering path; creates clusters the v6.x retrieval path ignores
- `!debug summarize_clusters` — depended on `!debug clusters` clusters

**Fixed:**
- `!summary full` docstring: "archived topics" → "key facts"
- `!summary create` result: removed "Pipeline: cluster-v5" label + dead v4.x else branch
- README: topic-based → segment-based retrieval description; pipeline description updated; "no API refetch on restart" fixed; `AI_PROVIDER` default `deepseek` → `openai`

**Modified:** `summary_commands.py` v2.5.0, `cluster_commands.py` v1.5.0, `debug_commands.py` v1.9.0

---

### Version 6.2.0 — SQLite FTS5 Hybrid Search + RRF Fusion

Adds BM25 keyword retrieval via SQLite FTS5, fused with dense retrieval via
Reciprocal Rank Fusion. Addresses keyword recall gaps where segment syntheses
paraphrase original terms.

**Retrieval flow (`_retrieve_segment_context` in `context_retrieval.py`):**
1. Embed query via `embed_query_with_smart_context()` (unchanged)
2. `find_relevant_segments(top_k * 2)` — cosine vs all segment embeddings, floor 0.20
3. `_apply_score_gap()` — cut dense candidates at largest inter-score gap ≥ 0.08
4. `fts_search(query_text)` — BM25 via FTS5; matches synthesis + raw message text
5. `rrf_fuse(dense, bm25, k=RRF_K)` — rank-based fusion; returns top-K fused IDs
6. Per fused segment: `get_segment_with_messages()` → synthesis + source messages
7. BM25-only segments (not in dense pool) resolved from seg_data dict
8. Inject `[Topic: label]\nSummary: ...\n\nSource messages:\n[N] ...`
9. Synthesis-only fallback when token budget is tight

**FTS5 index:** populated by `populate_fts()` in `utils/fts_search.py` during
`!summary create`. Failure degrades gracefully to dense-only (empty BM25 list
leaves RRF fusion unchanged).

**Rollback path:** if no segments in DB (pre-v6 channel), `_cluster_rollback()`
fires and uses `find_relevant_clusters()` + `get_cluster_messages()`.

**New config:** `RRF_K=15`
**New files:** `utils/fts_search.py` v1.0.0, `schema/009.sql`
**Modified:** `context_retrieval.py` v1.7.0, `summarizer.py` v4.2.0, `config.py` v1.18.0

---

### Version 6.1.0 — Direct Segment Retrieval + Top-K

Retrieval hot path changed from cluster centroid scoring to direct segment
embedding scoring. Query is scored against all segment embeddings (not 15
centroids), returning top-K with optional score-gap cutoff.

**Retrieval flow (`_retrieve_segment_context` in `context_retrieval.py`):**
1. Embed query via `embed_query_with_smart_context()` (unchanged)
2. `find_relevant_segments()` — cosine vs all segment embeddings, floor 0.20
3. `_apply_score_gap()` — cut at largest inter-score gap ≥ 0.08 (configurable)
4. Per segment: `get_segment_with_messages()` → synthesis + source messages
5. Inject `[Topic: label]\nSummary: ...\n\nSource messages:\n[N] ...`
6. Synthesis-only fallback when token budget is tight

**Rollback path:** if no segments in DB (pre-v6 channel), `_cluster_rollback()`
fires and uses `find_relevant_clusters()` + `get_cluster_messages()`.

**New config:** `RETRIEVAL_FLOOR=0.20`, `RETRIEVAL_SCORE_GAP=0.08`, `RETRIEVAL_TOP_K=7`
**Modified:** `cluster_retrieval.py` v1.2.0, `context_retrieval.py` v1.6.0,
`explain_commands.py` v1.2.0, `config.py` v1.17.0

---

### Version 6.0.0 — Conversation Segmentation Pipeline

Replaced per-message embeddings with per-segment embeddings for summarization
and retrieval. Gemini identifies topically coherent groups of consecutive messages
(segments), writes a synthesis resolving implicit references, then UMAP+HDBSCAN
clusters segments for retrieval. Existing `message_embeddings` and `cluster_messages`
tables are retained for rollback.

**New `!summary create` pipeline:**
1. Segment — Gemini batch-processes messages (500/batch, 20 overlap) → topic boundaries + synthesis
2. Embed segments — OpenAI embeds each synthesis
3. Cluster segments — UMAP+HDBSCAN on segment embeddings → `cluster_segments` junction
4. Summarize clusters — Gemini per cluster using segment syntheses as M-labeled inputs
5. Classify → overview → dedup → QA → save (unchanged from v5.x)

**Retrieval injection format per segment:**
```
[Topic: label]
Summary: synthesis text

Source messages:
[N] [date] author: content
```
Synthesis-only fallback when token budget is tight. Pre-v6 clusters (no segments) fall back to direct message injection.

**New tables:** `segments`, `segment_messages`, `cluster_segments` (`schema/008.sql`).
**New files:** `utils/segment_store.py` v1.0.0, `utils/segmenter.py` v1.0.0
**Modified:** `cluster_engine.py` v1.2.0 (+_adaptive_params(), scales UMAP/HDBSCAN to
input size), `cluster_summarizer.py` v1.1.0, `cluster_retrieval.py` v1.1.0,
`context_retrieval.py` v1.5.0, `cluster_overview.py` v2.3.0, `summarizer.py` v4.1.0,
`cluster_commands.py` v1.4.0 (`!debug segments`), `config.py` v1.16.0

After deploy: run `!summary create` to rebuild with segment-based clusters.

---

### Version 5.11.0 — History Package Consolidation

Removed 3 passthrough indirection files from `utils/history/` and trimmed
`management_utilities.py` to its single active function. The package public
API (`from utils.history import X`) is unchanged — only the intermediate hops
are gone.

**Deleted files:**
- `utils/history/api_imports.py` v1.3.0 — pure wildcard re-import passthrough, single caller (`__init__.py`)
- `utils/history/api_exports.py` v1.3.0 — pure `__all__` definition, single consumer (`__init__.py`)
- `utils/history/loading.py` v2.5.0 — passthrough; `load_channel_history()` moved to `channel_coordinator.py`
- `utils/history/loading_utils.py` v1.3.0 — 3 functions (`get_loading_status`, `force_reload_channel_history`, `get_history_statistics`) with zero external callers; exported only via the now-deleted passthrough layer

**Modified files:**
- `utils/history/__init__.py` v3.2.0 — rewritten with direct imports; `__all__` trimmed from ~40 symbols to the 11 that external code actually imports
- `utils/history/channel_coordinator.py` v2.1.0 — added `load_channel_history()` public API function (moved from deleted `loading.py`)
- `utils/history/management_utilities.py` v2.0.0 — stripped from 5 functions to 1; 4 dead functions removed, `validate_setting_value()` kept (called by `settings_manager.py`)

**Schema:**
- `schema/007.sql` — drops `topics` and `topic_messages` tables (v4.x relics, replaced by clusters in v5.5.0, no active code since v5.10.0)

### Post-5.11.0 Fixes

- `commands/status_commands.py` v2.2.0: fixed `get_thinking_enabled` import — was `from utils.history import ...` (never exported there); corrected to `from commands.thinking_commands import ...`
- `utils/embedding_store.py` v1.9.1: corrected stale v1.8.0 changelog entry referencing `topic_store.py` (deleted v5.10.0)
- `config.py` v1.14.0: updated default Gemini model names to `gemini-3.1-flash-lite-preview`

---

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
- `utils/history/diagnostics.py` v1.0.0 — 4 dev diagnostic helpers (`get_channel_diagnostics`, `identify_potential_issues`, `estimate_memory_usage`, `analyze_channel_health`) with no command callers since extraction in v2.x. Removed import chain from `__init__.py` and `loading_utils.py` (itself deleted in v5.11.0).

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
├── bot.py                         # v3.4.0
├── config.py                      # v1.18.0
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
│   ├── 006.sql                    # v5.4.0 needs_resummarize column
│   ├── 007.sql                    # v5.11.0 drop topics, topic_messages
│   ├── 008.sql                    # v6.0.0 segments, segment_messages, cluster_segments
│   └── 009.sql                    # v6.2.0 segments_fts FTS5 virtual table
├── ai_providers/
│   ├── __init__.py                # v1.5.0
│   ├── openai_provider.py         # v1.4.0
│   ├── anthropic_provider.py      # v1.1.0
│   ├── openai_compatible_provider.py  # v1.2.0
│   └── gemini_provider.py         # v1.2.1
├── commands/
│   ├── __init__.py                # v2.7.0
│   ├── summary_commands.py        # v2.5.0
│   ├── debug_commands.py          # v1.9.0
│   ├── cluster_commands.py        # v1.6.0
│   ├── dedup_commands.py          # v1.0.0
│   ├── explain_commands.py        # v1.1.0
│   ├── auto_respond_commands.py   # v2.2.0
│   ├── ai_provider_commands.py    # v2.1.0
│   ├── thinking_commands.py       # v2.2.0
│   ├── prompt_commands.py         # v2.2.0
│   ├── status_commands.py         # v2.2.0
│   └── history_commands.py        # v2.1.0
├── utils/
│   ├── citation_utils.py          # v1.0.0
│   ├── receipt_store.py           # v1.0.0
│   ├── proposition_store.py       # v1.0.0  ← new v6.4.0
│   ├── proposition_decomposer.py  # v1.0.0  ← new v6.4.0
│   ├── fts_search.py              # v1.1.0
│   ├── segment_store.py           # v1.0.1
│   ├── segmenter.py               # v1.0.0
│   ├── cluster_engine.py          # v1.1.0
│   ├── cluster_store.py           # v2.0.0
│   ├── cluster_summarizer.py      # v1.1.0
│   ├── cluster_overview.py        # v2.3.0
│   ├── cluster_classifier.py      # v1.6.0
│   ├── cluster_qa.py              # v1.0.0
│   ├── cluster_assign.py          # v1.0.0
│   ├── cluster_update.py          # v1.0.0
│   ├── cluster_retrieval.py       # v1.2.0
│   ├── logging_utils.py           # v1.1.0
│   ├── models.py                  # v1.3.0
│   ├── message_store.py           # v1.2.0
│   ├── raw_events.py              # v1.8.0
│   ├── db_migration.py            # v1.0.0
│   ├── embedding_store.py         # v1.10.0
│   ├── embedding_noise_filter.py  # v1.0.0
│   ├── embedding_context.py       # v1.5.0
│   ├── context_retrieval.py       # v1.8.0
│   ├── context_manager.py         # v2.5.2
│   ├── response_handler.py        # v1.4.0
│   ├── summarizer.py              # v4.2.0
│   ├── summary_store.py           # v1.1.0
│   ├── summary_display.py         # v1.3.2
│   └── history/
│       ├── message_processing.py       # v2.3.0
│       ├── realtime_settings_parser.py # v2.2.0
│       ├── channel_coordinator.py      # v2.1.0
│       ├── management_utilities.py     # v2.0.0
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
Citations work reliably with Anthropic (Claude). DeepSeek Reasoner and
gpt-4o-mini consistently ignore `[N]` citation instructions — this is accepted
as a model limitation. Users who want citation-backed responses should select
Anthropic as their channel provider via `!ai anthropic`.

### 2. Hierarchical Semantic Memory
Channel summaries are flat and per-channel. No cross-channel memory, no
user-level memory, no long-term summarization surviving `!summary create` wipe.

### 3. Legacy Cluster Noise
Thin messages and deleted placeholders embedded before v5.13.0 may remain
in existing clusters. Run `!debug reembed` + `!summary create` in affected
channels to rebuild clusters with the new noise filter applied.

---

For detailed version history prior to v5.9.0, see git log.
