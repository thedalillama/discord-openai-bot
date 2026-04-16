# AGENT.md
# Version 6.4.1
# Agent Development Rules for Discord Bot Project

## Core Agent Principles

### 1. MANDATORY APPROVAL PROCESS
- NO CODE CHANGES WITHOUT APPROVAL
- Present proposed changes with rationale and impact assessment
- Wait for explicit approval before implementing
- If uncertain, always ask first

### 2. DISCUSSION-FIRST APPROACH
- Discuss the problem, proposed solution, and alternatives before coding
- Explain reasoning behind technical decisions
- Consider impact on existing functionality and architecture

## Git Workflow

### 3. BRANCH MANAGEMENT
- `main` branch: Stable, production-ready code only
- `development` branch: Primary development branch
- Feature branches (e.g. `claude-code`): For isolated work streams
- Never commit untested code to `main`

### 4. DEVELOPMENT PROCESS
- Develop and test in `development` or feature branches
- Commit frequently with clear, descriptive messages
- Test all functionality before considering merge to `main`
- `main` should always be deployable

### 5. RELEASE WORKFLOW
- All development stays in branch until fully tested
- Validate existing functionality after changes
- Tag releases in `main` for version tracking (v2.x, v3.x, v4.x)

## Code Standards

### 6. FILE AND CODE REQUIREMENTS
- 250-line file limit — mandatory for all files
- Single responsibility — each module serves one clear purpose
- Comprehensive docstrings and inline comments
- Module-specific logging with appropriate levels
- Graceful error handling and recovery
- Version header in every file (e.g. `# Version 1.2.0`)
- Increment version on every change
- Update changelog in docstring

### 7. ASYNC SAFETY
- All provider API calls wrapped in `run_in_executor()`
- Never block the Discord event loop with synchronous calls
- All SQLite operations via `asyncio.to_thread()`

### 8. PREFIX TAGGING
- All bot command output must be prefixed:
  - `ℹ️` — informational/noise (filter from API, summarizer, everything)
  - `⚙️` — settings changes (keep for replay, filter from API/summarizer)
- New commands must use these prefixes on all `ctx.send()` calls
- This replaces pattern-matching for noise filtering

### 9. DOCUMENTATION
- **Update README.md, STATUS.md, HANDOFF.md, and README_ENV.md alongside every code change**
- Keep CLAUDE.md current for Claude Code sessions
- Full files only — never partial diffs or patches
- Always provide complete file contents when delivering changes

### 10. MAINTAIN CONSISTENCY
- Follow established patterns and conventions
- Respect modular architecture and file organization
- Maintain backward compatibility with existing APIs and imports

## Current Architecture Context

### Semantic Retrieval (v6.4.1 — proposition+dense+BM25+RRF)
- Retrieval path: `context_manager.py` → `_retrieve_segment_context()` in `context_retrieval.py`
- Query embedded via `embed_query_with_smart_context()` → (vec, path_name)
- Propositions: `find_relevant_propositions()` — cosine vs all prop embeddings; collapse to max-score-per-segment → seg IDs
- Dense: `find_relevant_segments(top_k*2, floor=RETRIEVAL_FLOOR)` — cosine vs all segment embeddings
- Score-gap: `_apply_score_gap()` — cuts at largest inter-score gap ≥ `RETRIEVAL_SCORE_GAP`
- BM25: `fts_search(query_text)` via SQLite FTS5 — synthesis + raw message content
- RRF: `rrf_fuse(prop, dense, bm25, k=RRF_K)` → top-K fused (segment_id, rrf_score) pairs
- Per segment: `get_segment_with_messages()` → synthesis + source messages injected with [N] citations
- Rollback: if no segments in DB, `_cluster_rollback()` scores query vs cluster centroids (RETRIEVAL_MIN_SCORE)
- Message fallback: `find_similar_messages()` when segment retrieval empty
- Receipt stored via `receipt_store.py`; `!explain` displays retrieved_segments + score_gap_applied

### Context Receipts & !explain (v5.7.0+)
- Every bot response stores a context receipt via `receipt_store.py`
- Receipt contains: query, embedding path, always-on counts, retrieved_segments (v6.1.0+) or
  retrieved_clusters (rollback), score_gap_applied, fallback info, token budget, provider/model
- Signal chain: `embed_query_with_smart_context()` → `_retrieve_segment_context()` →
  `build_context_for_provider()` → `(messages, receipt_data, citation_map)` →
  `handle_ai_response_task()` → `save_receipt()` after send
- `!explain` / `!explain detail` / `!explain <id>` — display via `format_receipt()` in `explain_commands.py`
- Receipt storage is fail-safe: never blocks or prevents bot responses

### Smart Query Embedding (v5.6.1)
- `embed_query_with_smart_context()` in `embedding_context.py` — two-path logic:
  Path 1 (question detection via `is_question()`), Path 2 (cosine similarity check
  vs previous stored embedding via `get_stored_embedding()`)
- `QUERY_TOPIC_SHIFT_THRESHOLD` (default 0.5) controls topic-shift detection (SOW v5.12.0)
- `build_contextual_text()` uses `EMBEDDING_CONTEXT_MIN_SCORE` (default 0.3) for
  context-window filtering of previous messages (SOW v5.12.0)

### Context-Prepended Embeddings (v5.6.0)
- All messages embedded with conversational context via `build_contextual_text()`
  in `utils/embedding_context.py` (format: `[Context: a1: msg1 | ...]\nauthor: content`)
- Reply chains: replied-to message used as primary context
- Query embedding also contextual: last 3 in-memory conversation messages prepended
- `!debug reembed` + `!summary create` required after deploy to rebuild embeddings/clusters
- `utils/context_retrieval.py` — retrieval extracted from context_manager.py
- `commands/cluster_commands.py` — cluster commands extracted from debug_commands.py

### Noise Guard (v5.13.0)
- `utils/embedding_noise_filter.py` `should_skip_embedding()` — single gate
  for what gets embedded; applied in `raw_events.py` (live) and
  `embedding_store.py` `get_messages_without_embeddings()` (backfill)
- Skip criteria: empty, `!`/`ℹ️`/`⚙️` prefix, bot diagnostic prefixes,
  `[Original Message Deleted]` placeholder, fewer than 4 words (questions exempt)
- `debug_commands.py` v1.6.0 routes all pagination through `send_paginated()`
  to guarantee ℹ️ on every chunk

### Segment Pipeline (v6.0.0)
- `!summary create` now runs: segment → embed segments → cluster segments → summarize (use_segments=True) → classify → overview → dedup → QA → save
- `utils/segmenter.py` `run_segmentation_phase()` — Gemini batch-processes messages (SEGMENT_BATCH_SIZE, SEGMENT_OVERLAP) into segments with topic labels and syntheses; syntheses resolve implicit references ("yes" → "Alice agreed to use PostgreSQL")
- `utils/segment_store.py` — CRUD for `segments`, `segment_messages`, `cluster_segments` tables; `run_segment_clustering()` runs UMAP+HDBSCAN on segment embeddings, stores to `clusters` + `cluster_segments` without touching `cluster_messages`
- Retrieval injects per-segment `[Topic: label]\nSummary: synthesis\n\nSource messages:\n[N] [date] author: content`; synthesis-only fallback when budget is tight; rollback path (no segments) falls back to direct message injection

### Cluster Rollback Path (pre-v6 channels)
- Fires when `find_relevant_segments()` returns empty (no segments in DB)
- `_cluster_rollback()` in `context_retrieval.py` → `find_relevant_clusters()` + `get_cluster_messages()`
- Filters by `RETRIEVAL_MIN_SCORE` (production: 0.5); receipt uses `retrieved_clusters` key
- `[Topic: {label}]` section header preserved — model framing unchanged

### Incremental Assignment (v5.4.0)
- New messages assigned to nearest cluster centroid on arrival (`raw_events.py` →
  `cluster_assign.py`); centroid updated via running average + renormalize; cluster
  flagged `needs_resummarize=1`
- `!summary update` re-summarizes only dirty clusters (Tier 2), no re-cluster
- `schema/006.sql`: `ALTER TABLE clusters ADD COLUMN needs_resummarize INTEGER DEFAULT 0`
- Key files: `cluster_assign.py`, `cluster_update.py`, `cluster_store.py` v2.0.0

### Summarization Pipeline (v5.3.0 — cluster-based)
- `!summary create` → `summarizer.py` → `run_cluster_pipeline()` in `cluster_overview.py`
- UMAP + HDBSCAN clustering → per-cluster Gemini summarization → classify → overview → dedup → QA → save
- Classifier (`cluster_classifier.py`): GPT-4o-mini whitelist filter; default-to-DROP on missing verdict
- Overview LLM receives labels + summary texts only (not structured fields) — prevents 16K+ token blowup
- Dedup (`cluster_qa.py`): embedding cosine similarity, 0.85 threshold, all four arrays
- Answered-Q check (`cluster_qa.py`): GPT-4o-mini YES/NO, removes questions answered by facts/decisions
- Field translation at storage time: `text` → `fact`/`task`/`question`/`decision` (v4.x display layer unchanged)
- v4.x three-pass pipeline removed in v5.10.0 (10 files deleted, git history preserves)

### Clustering Core (v5.1.0)
- `utils/cluster_engine.py` — UMAP (cosine, 1536→5 dims) + HDBSCAN (euclidean, eom)
- Noise reduction: noise points reassigned to nearest centroid above RETRIEVAL_MIN_SCORE
- `utils/cluster_store.py` — CRUD, run_clustering() orchestrator, format_cluster_report()
- `schema/005.sql` — clusters + cluster_messages tables (alongside v4.x topics)

### Conversation Providers
- OpenAI, Anthropic, DeepSeek — per-channel configurable
- Provider singleton caching, async executor wrapping
- Token-budget context: always-on + retrieved + 5 recent messages

### Startup & Persistence (v6.4.1)
- SQLite with WAL mode, thread-local connections (`message_store.py` v1.3.0)
- Tables: messages, summaries, embeddings, clusters, cluster_messages, segments, segment_messages, cluster_segments, propositions
- On startup: settings restored from SQLite (`restore_settings_from_db()` — queries ⚙️ bot messages); Discord fetched delta-only after `last_processed_id`; in-memory history seeded from DB (last MAX_HISTORY×10 messages, filtered)
- Prefix system (ℹ️/⚙️) for noise vs settings classification

## REMEMBER:
1. NO CODE CHANGES WITHOUT APPROVAL!
2. ALL DEVELOPMENT IN `development` OR FEATURE BRANCHES
3. `main` BRANCH IS FOR STABLE CODE ONLY
4. DISCUSS FIRST, CODE SECOND
5. 250-LINE LIMIT AND MODULAR PATTERNS
6. PREFIX ALL BOT OUTPUT WITH ℹ️ OR ⚙️
7. **UPDATE ALL DOCUMENTATION BEFORE MERGING**

For Technical Details: See README.md and STATUS.md
For Current State: See HANDOFF.md
For Environment Config: See README_ENV.md
For Claude Code: See CLAUDE.md
For Agent Workflow: This document
