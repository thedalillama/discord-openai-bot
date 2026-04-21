# STATUS.md
# Discord Bot Development Status
# Version 7.1.0

## Current Version Features

### Version 7.1.0 — Entity State Machine (M2)

**Explicit segment status tracking:**
`segments` table now has a `status` column tracking pipeline progress:
`created` → `embedded` → `propositioned` → `indexed` → `clustered`/`unclustered`.
`summarizer.py` sets status after each stage; `run_segment_clustering` sets
`clustered`/`unclustered` via SQL JOIN after UMAP+HDBSCAN completes.

**Cluster status helpers:**
`update_cluster_status` and `get_cluster_status_counts` added to `cluster_store.py`.
Cluster status (`active`/`archived`/`dirty`/`dropped`) was already set by the LLM
during summarization — M2 adds query helpers and indexes for it.

**`!debug pipeline` enhanced:**
Now shows segment and cluster status counts:
```
Segments: 78 total (78 clustered)
Clusters: 11 total (1 active, 0 dirty, 0 dropped)
```

**One-time migration (`schema/012.sql`):**
Existing segments correctly initialized from DB state — segments in
`cluster_segments` set to `clustered`; segments with embeddings but no cluster
set to `unclustered`; remainder set to `embedded`. No `!summary create` needed.

**Dead code removed:**
`format_cluster_report` deleted from `cluster_store.py` — had no callers since
`!debug clusters` was removed in v6.3.0.

**`get_cluster_content` consolidated:**
Moved from `segment_store.py` into `cluster_retrieval.py` (was already a
delegate wrapper there). `cluster_retrieval.py` is now the single home for
all cluster/segment retrieval queries.

**Files changed:**
- `schema/012.sql` NEW — segments status column + indexes + migration
- `utils/segment_store.py` v1.0.1 → v1.1.0
- `utils/cluster_retrieval.py` v1.3.0 → v1.4.0
- `utils/cluster_store.py` v2.0.0 → v2.1.0
- `utils/summarizer.py` v4.5.0 → v4.6.0
- `utils/cluster_classifier.py` v1.6.0 → v1.7.0
- `commands/debug_commands.py` v2.0.0 → v2.1.0

---

### Version 7.0.1 — Layer 2 Fixes + Pipeline State + UMAP Process Pool

**`_msg_id` threading for Layer 2 deduplication:**
Discord message IDs are now threaded through every message dict in
`channel_history` (`_msg_id` key). `prepare_messages_for_api()` passes them
through. `build_context_for_provider()` builds `layer2_ids` from the continuity
block and filters `selected` (conversation history) against it — Layer 2 is
canonical; in-memory history only contributes messages too new to be in SQLite.

**Dedup direction corrected:**
Previously Layer 2 messages were dropped in favour of in-memory history copies.
Fixed: `selected` is filtered against `layer2_ids`. Layer 2 turns (timestamped,
from SQLite) are always kept; only truly unseen recent messages come from memory.

**Layer 2 noise filter:**
`get_unsummarized_messages()` and `get_session_bridge_messages()` in
`pipeline_state.py` now skip ℹ️/⚙️-prefixed bot output and `!` commands —
matching the same rules as `_seed_history_from_db()`. Bot command echoes and
admin output no longer appear as conversation turns in Layer 2.

**`save_pipeline_state` after `!summary create`:**
`summarize_channel()` captures `max_msg_id = messages[-1].id` before the
pipeline runs, then calls `save_pipeline_state(channel_id, max_msg_id, now)`
after a successful run. Layer 2's "unsummarized" window now correctly starts
at the end of the just-completed segmentation — not at the v6 pointer.

**ProcessPoolExecutor for UMAP (GIL-free clustering):**
`asyncio.to_thread` shares the GIL; 45-second UMAP runs blocked the Discord
event loop and caused gateway disconnects during `!summary create`. A shared
`ProcessPoolExecutor(max_workers=1)` — `_cluster_pool` in `cluster_engine.py`
— is now used for both `run_segment_clustering()` (in `summarizer.py`) and
`run_clustering()` (in `cluster_overview.py`) via `run_in_executor()`.

**`!explain` always-on token count fix:**
Receipt dict was missing `total_tokens` — `explain_commands.py` read that key
but it was never set. Fixed: `total_tokens = always_on_tokens + control_tokens`
added to the `always_on` sub-dict in `receipt_data`.

**Full context JSON dump at DEBUG:**
After assembling `final_messages`, `context_manager.py` writes
`/tmp/last_full_context.json` when log level is DEBUG. Useful for inspecting
exactly what the model receives.

**Files changed:**
- `utils/context_manager.py` v3.0.0 → v3.0.3
- `utils/pipeline_state.py` v1.0.0 → v1.1.0
- `utils/history/message_processing.py` v2.3.0 → v2.4.0
- `utils/history/discord_loader.py` v2.3.0 → v2.4.0
- `utils/history/discord_converter.py` v1.0.0 → v1.1.0
- `utils/response_handler.py` v1.4.0 → v1.5.0
- `utils/message_utils.py` v1.1.0 — added `msg_id` param
- `utils/summarizer.py` v4.3.0 → v4.5.0
- `utils/cluster_engine.py` v1.2.0 → v1.3.0
- `utils/cluster_overview.py` v2.4.0 → v2.5.0
- `bot.py` — `format_user_message_for_history` calls pass `msg_id=message.id`

---

### Version 7.0.0 — Three-Layer Context Injection (M1)

**Three-layer context assembly:**
Context is now assembled in priority order — Layer 1 (system + control file +
always-on summary) is always guaranteed. Layer 2 (session bridge + unsummarized
messages) is budget-guaranteed and injected as message turns before the
conversation history. Layer 3 (historical RRF retrieval) fills whatever budget
remains. Recent messages are never trimmed in favour of old history.

**Session bridge:** The bot injects raw source messages from the most recent
conversation session's segments, bridging the gap between what's summarized and
what's live in memory. Pronoun references resolve naturally across the summary
boundary.

**Unsummarized injection:** All messages after `last_segmented_message_id` are
injected as Layer 2 turns. The bot never says "I don't have context" about recent
messages that are already in the DB.

**Operator control file:** Create `data/control.txt` to inject arbitrary text
into every system prompt. Useful for channel-specific standing instructions.
Missing or empty file = no injection.

**`!debug pipeline`:** Shows pipeline state for the current channel —
last segmented message ID, unsummarized message count, last pipeline run,
summary status, session bridge message count.

**New files:** `utils/pipeline_state.py` (pipeline CRUD + session bridge queries),
`utils/context_helpers.py` (context assembly helpers), `utils/cluster_fallback.py`
(extracted v5 cluster rollback path), `schema/011.sql` (pipeline_state table).

---

### Version 6.4.2 — Benchmark Score Fix + History Seeding

**Benchmark score-scale corrected (v6.4.0/v6.4.1 regression):**
`retrieval_benchmark.py` v6.4.0 mistakenly put the RRF fused score (~0–0.19
with `RRF_K=15`) in the "top_score" slot instead of the dense cosine score
(0–1). v6.4.2 carries separate `cosine_score` and `rrf_score` in every segment
5-tuple, reports cosine as the primary cross-version metric, and includes a
`score_note` in the JSON output documenting the prior confusion.

**Benchmark v6.4.2 baseline:**
- Avg top cosine score: 0.391 (16/16 queries have cosine)
- Avg keyword recall: 60%
- Empty retrievals: 0/16
- Avg latency: 2328ms

**"No conversation history" bug fixed:**
After a restart where the delta fetch returned 0 new messages, `channel_history`
was empty — the bot replied "No conversation history available." Fixed by
`_seed_history_from_db(channel_id)` which loads the last `MAX_HISTORY × 10`
messages from SQLite, filters noise/commands, and seeds the last `MAX_HISTORY`
valid entries into memory before the Discord fetch.

**`!history` 2000-char overflow fixed:**
Message content is now truncated to 350 chars before building history entries,
preventing individual entries from exceeding Discord's 2000-char send limit.

**`cluster_diagnostic.py` deleted:**
Pre-v6 decision tool that classified cluster quality (NOISE/WEAK/MODERATE/STRONG)
to determine if segmentation was needed. Decision shipped; reads `cluster_messages`
which is never populated in the v6 segment pipeline.

**Files changed:**
- `utils/history/discord_loader.py` v2.2.0 → v2.3.0 (`_seed_history_from_db`)
- `commands/history_commands.py` v2.1.0 → v2.2.0 (350-char content truncation)
- `retrieval_benchmark.py` v2.0.0 (entry point only; split into 3 files)
- `benchmark_queries.py` v1.0.0 (new — extracted `BENCHMARK_QUERIES`)
- `benchmark_core.py` v1.0.0 (new — `run_query`, `score_result`, helpers)
- `cluster_diagnostic.py` deleted

---

### Version 6.4.1 — Startup Fetch Optimization

Eliminates the full Discord channel history fetch on restart. Previously, the
bot fetched every message from every channel's history just to find ⚙️ settings
confirmation messages. With 2000+ messages per channel this was slow and
unnecessary.

**New flow:**
1. `restore_settings_from_db(channel_id)` — queries SQLite for `is_bot_author=1`
   + `content LIKE '⚙️%'` messages (up to 200, newest-first). Wraps rows as
   duck-typed objects and passes to `parse_settings_during_load()`. Settings
   applied without touching Discord.
2. `fetch_messages_from_discord(channel, is_automatic, after_id=last_id)` —
   delta fetch via `channel.history(after=discord.Object(id=last_id), oldest_first=True)`.
   Only pulls messages that arrived since the last DB-recorded message ID.
3. Any ⚙️ messages in the delta (rare: would have to arrive between backfill and
   history load) are still parsed and applied.

**Modified:**
- `utils/history/realtime_settings_parser.py` v2.2.0 → v2.3.0 (new `restore_settings_from_db`)
- `utils/history/discord_fetcher.py` v1.2.0 → v1.3.0 (`after_id` param, `import discord`)
- `utils/history/discord_loader.py` v2.1.0 → v2.2.0 (orchestration using new functions)

**Also shipped in v6.4.x (bug fixes / observability):**
- `message_store.py` v1.3.0: thread-local SQLite connections fix `SQLITE_MISUSE`
- `raw_events.py` v1.9.0: `get_last_processed_id` inside try block so backfill errors are logged
- `cluster_summarizer.py` v1.2.0: log segment count instead of stale `message_count`
- `segmenter.py` v1.0.3: log each dropped message on partial segment coverage
- `proposition_decomposer.py` v1.1.0: retry proposition embedding once after 5s on 503
- `cluster_overview.py` v2.4.0: pipeline label from meta instead of hardcoded `cluster-v5`
- `summary_display.py` v1.3.3: read pipeline label from summary meta
- `retrieval_benchmark.py`: version-stamped benchmark results under `benchmarks/`

---

### Version 6.4.0 — Proposition Decomposition (SOW v6.3.0)

Adds proposition-level embeddings as a third retrieval signal alongside
dense segment embeddings and BM25 keyword search. Each segment synthesis
is decomposed into 3-5 atomic, self-contained claims by GPT-4o-mini. Each
claim gets its own embedding. At query time, propositions are scored against
the query and collapsed to max-score-per-segment before entering RRF fusion.

**Why:** Segment syntheses cover multiple subtopics in one vector. A compound
query like "what did OpenClaw say about databases?" fails because no segment
scores well on both dimensions simultaneously. Propositions are narrow —
"OpenClaw confirmed the PostgreSQL choice" and "the team chose PostgreSQL"
are separate vectors with focused semantics.

**Collapse-before-RRF:** `find_relevant_propositions()` keeps only the best
proposition per segment. Each segment appears at most once in the proposition
signal regardless of proposition count — no size bias.

**Three-signal retrieval flow:**
1. `find_relevant_propositions()` — prop cosine → collapse to seg IDs
2. `find_relevant_segments(top_k*2)` — segment cosine → seg IDs
3. `fts_search()` — BM25 keyword → seg IDs
4. `rrf_fuse(prop, dense, bm25)` — rank fusion → top-K fused IDs
5. Fetch + inject segment content as before

**Pipeline addition in `summarizer.py`:**
After FTS5 population and before segment clustering:
`run_proposition_phase(channel_id, progress_fn)` — decompose → store → embed.
Failure degrades to two-signal (dense + BM25); pipeline continues regardless.

**New config:** `PROPOSITION_BATCH_SIZE=10`, `PROPOSITION_PROVIDER=openai`
**New files:** `utils/proposition_store.py` v1.0.0,
`utils/proposition_decomposer.py` v1.0.0, `schema/010.sql`
**Modified:** `cluster_retrieval.py` v1.3.0, `context_retrieval.py` v1.8.0,
`fts_search.py` v1.1.0, `summarizer.py` v4.3.0, `config.py` v1.19.0,
`cluster_commands.py` v1.6.0 (`!debug propositions`)

After deploy: run `!summary create` to rebuild with propositions.

---

### Version 6.3.0 — Dead Command Removal + Doc Accuracy

Removed obsolete commands and fixed stale descriptions exposed during a
documentation audit.

**Removed commands:**
- `!summary raw` — `minutes_text` field never written by the v5.x+ pipeline
  (Secretary was removed in v5.10.0); always returned "No raw minutes."
- `!debug clusters` — ran `run_clustering()` from `cluster_store.py`, which
  uses message embeddings (v5.x path). In v6.x channels this creates a parallel
  cluster set that the retrieval path (`_retrieve_segment_context`) never reads.
  Zero diagnostic value post-v6.0.
- `!debug summarize_clusters` — depended on clusters created by `!debug clusters`;
  removed alongside it.

**Fixed stale descriptions:**
- `!summary full`: "archived topics" → "key facts" (topics removed v5.10.0)
- `!summary create` result: "Pipeline: cluster-v5" label + dead v4.x else branch
  removed; result now displays cluster/noise/message counts without a stale label.

**Fixed README inaccuracies:**
- Features: "topic-based retrieval" → "segment-based hybrid retrieval (BM25+dense+RRF)"
- Features: "three-pass Secretary/Structurer/Classifier pipeline" → current segment+cluster pipeline description
- Features: "surviving restarts without API refetch" → accurate description of Discord history backfill on restart
- Config table: `AI_PROVIDER` default `deepseek` → `openai` (matches `config.py`)

**Modified:** `summary_commands.py` v2.5.0, `cluster_commands.py` v1.5.0,
`debug_commands.py` v1.9.0

---

### Version 6.2.0 — SQLite FTS5 Hybrid Search + RRF Fusion

Adds BM25 keyword matching via SQLite FTS5 to complement dense embedding
retrieval. Dense retrieval excels at semantic similarity; BM25 excels at
exact keyword matches ("gorillas", "PostgreSQL") that segment syntheses
paraphrase away. Combining them via Reciprocal Rank Fusion improves recall
without degrading precision on abstract queries.

**New retrieval flow in `_retrieve_segment_context()`:**
1. Dense: `find_relevant_segments(top_k * 2)` — expanded candidate pool
2. `_apply_score_gap()` — prune dense candidates
3. BM25: `fts_search(query_text)` — keyword matches against synthesis + raw messages
4. `rrf_fuse(dense, bm25, k=RRF_K)` — rank-based fusion, score-agnostic
5. Fetch content for fused segment IDs; inject as before
6. BM25-only segments (not in dense results) resolved from seg_data dict

**FTS5 index:** `segments_fts` table populated during `!summary create` via
`populate_fts()` in `utils/fts_search.py`. Searchable text = synthesis + " --- "
+ raw message content. Failure degrades gracefully to dense-only.

**New config:** `RRF_K` (default 15).
**New files:** `utils/fts_search.py` v1.0.0, `schema/009.sql`
**Modified:** `context_retrieval.py` v1.7.0, `summarizer.py` v4.2.0, `config.py` v1.18.0

After deploy: run `!summary create` to populate FTS5 index.

### Post-6.2.0 Fixes

- `bot.py` v3.4.0: Wrapped both `build_context_for_provider()` call sites in
  `asyncio.to_thread()` — synchronous retrieval (SQLite + OpenAI HTTP) was blocking
  the event loop, delaying heartbeat keepalives and causing WebSocket disconnects.
- `utils/context_manager.py` v2.5.2: Fixed `receipt_data` missing `retrieved_segments`
  and `score_gap_applied` keys — `!explain` was always showing "Retrieved Clusters (none)"
  even when segment retrieval succeeded, because only the old v5.x `retrieved_clusters`
  key was copied from the cluster receipt.

---

### Version 6.1.0 — Direct Segment Retrieval + Top-K

Replaced cluster centroid retrieval with direct segment embedding retrieval.
Instead of scoring a query against 15 averaged cluster centroids, the query
is scored against all ~150 individual segment embeddings, giving precise
per-topic similarity scores. Score-gap detection provides an adaptive
relevance cutoff after top-K selection.

**What changed on the retrieval path:**
- `find_relevant_segments()` — cosine vs all segment embeddings directly
- `_apply_score_gap()` — cuts at largest inter-score gap if ≥ RETRIEVAL_SCORE_GAP
- `get_segment_with_messages()` — per-segment content fetch
- Rollback: if no segments in DB, falls back to cluster centroid retrieval

**New config vars:** `RETRIEVAL_FLOOR` (default 0.20, floor for segment retrieval),
`RETRIEVAL_SCORE_GAP` (default 0.08, gap cutoff threshold), `RETRIEVAL_TOP_K` (default 7).

**Modified:** `cluster_retrieval.py` v1.2.0, `context_retrieval.py` v1.6.0
(renamed `_retrieve_segment_context`), `explain_commands.py` v1.2.0
(segment-aware receipt display), `config.py` v1.17.0

---

### Version 6.0.0 — Conversation Segmentation Pipeline

Replaced per-message embeddings with per-segment embeddings for summarization
and retrieval. Gemini identifies topically coherent groups of consecutive messages
(segments), writes a synthesis resolving implicit references, then UMAP+HDBSCAN
clusters segments for retrieval. Existing `message_embeddings` and `cluster_messages`
tables are retained for rollback.

**New `!summary create` pipeline:**
1. Segment — Gemini batch-processes messages → topic boundaries + synthesis
2. Embed segments — OpenAI embeds each synthesis
3. Cluster segments — UMAP+HDBSCAN on segment embeddings → `cluster_segments` junction
4. Summarize clusters — Gemini per cluster using segment syntheses as M-labeled inputs
5. Classify → overview → dedup → QA → save (unchanged from v5.x)

**Retrieval path:** `context_retrieval.py` injects `[Topic: label]\nSummary: synthesis\n\nSource messages:\n[N] [date] author: content` per segment. Synthesis-only fallback when budget is tight. Rollback path (pre-v6 clusters with no segments) falls back to direct message injection.

**New tables:** `segments`, `segment_messages`, `cluster_segments` (`schema/008.sql`).

**New files:** `utils/segment_store.py` v1.0.0 (CRUD + segment clustering),
`utils/segmenter.py` v1.0.0 (Gemini segmentation+synthesis, batch with overlap)

**Modified:** `cluster_engine.py` v1.2.0 (cluster_segments() + _adaptive_params()),
`cluster_summarizer.py` v1.1.0 (use_segments param), `cluster_retrieval.py` v1.1.0
(get_cluster_content()), `context_retrieval.py` v1.5.0 (segment injection),
`cluster_overview.py` v2.3.0 (pre_run_stats param), `summarizer.py` v4.1.0
(segment orchestration), `cluster_commands.py` v1.4.0 (!debug segments),
`config.py` v1.16.0 (segment vars)

After deploy: run `!summary create` to rebuild with segment-based clusters.

---

### Version 5.13.0 — Embedding Noise Filter Tightening

Added `utils/embedding_noise_filter.py` — a single authoritative gate for
what gets embedded. Replaces inline checks in `raw_events.py` and extends
coverage to the `!debug backfill`/`!debug reembed` paths.

New skip criteria (messages still stored in SQLite):
- `[Original Message Deleted]` bot-forwarded placeholders
- Messages with fewer than 4 words (unless ending with `?`)

Existing criteria consolidated from `raw_events.py`:
- Commands (`!` prefix), bot output (`ℹ️`/`⚙️`)
- Bot diagnostic prefixes + discord.py help output

After deploy, run `!debug reembed` + `!summary create` to rebuild clusters
without weak/noise content.

**Files changed:** `utils/embedding_noise_filter.py` v1.0.0 (new),
`utils/raw_events.py` v1.8.0, `utils/embedding_store.py` v1.10.0,
`AGENT.md`, `STATUS.md`, `HANDOFF.md`

---

### Version 5.12.0 — Similarity Threshold Rename & Separation

Renamed and split cosine similarity thresholds for clarity and independent
tuning. No behavioral change — all values unchanged.

- `CONTEXT_SIMILARITY_THRESHOLD` (hardcoded `0.3`) → `EMBEDDING_CONTEXT_MIN_SCORE`
  in `config.py`; now env-configurable.
- `RETRIEVAL_MIN_SCORE` (used for topic-shift detection) → `QUERY_TOPIC_SHIFT_THRESHOLD`
  (default `0.5`); `RETRIEVAL_MIN_SCORE` now exclusively controls cluster retrieval.
- `TOPIC_LINK_MIN_SCORE` comment updated to note it's legacy (topics table dropped
  in schema/007.sql).
- Fixed doc inconsistency: production `RETRIEVAL_MIN_SCORE=0.5` (was incorrectly
  documented as `0.45` in README.md and CLAUDE.md).
- Removed Known Limitation #3 (Context-Prepending Evaluation) — threshold is now
  configurable and properly named.

**Files changed:** `config.py` v1.15.0, `utils/embedding_context.py` v1.5.0,
`README.md`, `README_ENV.md`, `CLAUDE.md`, `AGENT.md`, `STATUS.md`, `HANDOFF.md`

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
├── config.py                      # v1.20.0
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
│   ├── 009.sql                    # v6.2.0 segments_fts FTS5 virtual table
│   ├── 010.sql                    # v6.4.0 propositions table
│   └── 011.sql                    # v7.0.0 pipeline_state table
├── ai_providers/
│   ├── __init__.py                # v1.5.0
│   ├── openai_provider.py         # v1.4.0
│   ├── anthropic_provider.py      # v1.1.0
│   ├── openai_compatible_provider.py  # v1.2.0
│   └── gemini_provider.py         # v1.2.1
├── commands/
│   ├── __init__.py                # v2.7.0
│   ├── summary_commands.py        # v2.5.0
│   ├── debug_commands.py          # v2.1.0  ← status counts in pipeline
│   ├── cluster_commands.py        # v1.6.0
│   ├── dedup_commands.py          # v1.0.0
│   ├── explain_commands.py        # v1.3.0
│   ├── auto_respond_commands.py   # v2.2.0
│   ├── ai_provider_commands.py    # v2.1.0
│   ├── thinking_commands.py       # v2.2.0
│   ├── prompt_commands.py         # v2.2.0
│   ├── status_commands.py         # v2.2.0
│   └── history_commands.py        # v2.2.0
├── utils/
│   ├── citation_utils.py          # v1.0.0
│   ├── receipt_store.py           # v1.0.0
│   ├── proposition_store.py       # v1.0.0
│   ├── proposition_decomposer.py  # v1.1.0
│   ├── fts_search.py              # v1.1.0
│   ├── segment_store.py           # v1.1.0  ← status helpers
│   ├── segmenter.py               # v1.0.3
│   ├── cluster_engine.py          # v1.3.0
│   ├── cluster_store.py           # v2.1.0  ← status helpers
│   ├── cluster_summarizer.py      # v1.2.0
│   ├── cluster_overview.py        # v2.5.0
│   ├── cluster_classifier.py      # v1.7.0
│   ├── cluster_qa.py              # v1.0.0
│   ├── cluster_assign.py          # v1.0.0
│   ├── cluster_update.py          # v1.0.0
│   ├── cluster_retrieval.py       # v1.4.0  ← get_cluster_content inlined
│   ├── cluster_fallback.py        # v1.0.0
│   ├── pipeline_state.py          # v1.1.0  ← Layer 2 noise filter
│   ├── context_helpers.py         # v1.0.0
│   ├── context_retrieval.py       # v1.9.0
│   ├── context_manager.py         # v3.0.3  ← dedup fix + receipt + JSON dump
│   ├── logging_utils.py           # v1.1.0
│   ├── models.py                  # v1.3.0
│   ├── message_store.py           # v1.3.0
│   ├── message_utils.py           # v1.1.0  ← msg_id param
│   ├── raw_events.py              # v1.9.0
│   ├── db_migration.py            # v1.0.0
│   ├── embedding_store.py         # v1.10.0
│   ├── embedding_noise_filter.py  # v1.0.0
│   ├── embedding_context.py       # v1.5.0
│   ├── response_handler.py        # v1.5.0  ← msg_id threading
│   ├── summarizer.py              # v4.6.0  ← entity status per stage
│   ├── summary_store.py           # v1.1.0
│   ├── summary_display.py         # v1.3.3
│   └── history/
│       ├── message_processing.py       # v2.4.0  ← msg_id + _msg_id passthrough
│       ├── discord_loader.py           # v2.4.0  ← msg_id in seed
│       ├── discord_converter.py        # v1.1.0  ← msg_id in convert
│       ├── realtime_settings_parser.py # v2.3.0
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
Command outputs that slipped through before v5.5.1/v1.7.0 may still be in
existing clusters. A `!summary create` in affected channels will re-cluster
from current embeddings, removing the noise.

---

For detailed version history prior to v5.9.0, see git log.
