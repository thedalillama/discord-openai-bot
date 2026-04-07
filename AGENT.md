# AGENT.md
# Version 5.10.0
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

### Semantic Retrieval (v4.1.x)
- Messages embedded on arrival via OpenAI `text-embedding-3-small`
- Topics cleared and re-linked on every `!summary create` — no duplicates accumulate
- Topics linked to all messages above `TOPIC_LINK_MIN_SCORE` (0.3) by cosine similarity
- Bot-noise topics filtered at retrieval time (`_is_noise_topic()` in `embedding_store.py`)
- At response time: always-on context (overview/facts/actions/questions) + retrieved topic messages
- Only topics above `RETRIEVAL_MIN_SCORE` (0.25) are injected; recent messages capped at 5
- Message fallback fires when no topics pass threshold OR all matched topics have 0 linked messages
- Each retrieved message prefixed with `[YYYY-MM-DD]`; today's date injected at top of context block
- `!debug backfill` batch-embeds 1000 messages per API call; re-links active + archived topics

### Context Receipts & !explain (v5.7.0)
- Every bot response stores a context receipt in `response_context_receipts` (schema 002.sql)
- Receipt contains: query, embedding path, always-on counts, retrieved clusters, below-threshold
  clusters, fallback info, recent message count, token budget, provider/model
- Signal chain: `embed_query_with_smart_context()` → `(vec, path_name)` →
  `_retrieve_cluster_context()` → `(text, tokens, cluster_receipt)` →
  `build_context_for_provider()` → `(messages, receipt_data)` →
  `handle_ai_response_task()` → `save_receipt()` after send
- `!explain` / `!explain <id>` — retrieve and display receipt via `format_receipt()`
- Receipt storage is fail-safe: never blocks or prevents bot responses

### Smart Query Embedding (v5.6.1)
- `embed_query_with_smart_context()` in `embedding_context.py` — two-path logic:
  Path 1 (question detection via `is_question()`), Path 2 (cosine similarity check
  vs previous stored embedding via `get_stored_embedding()`)
- `RETRIEVAL_MIN_SCORE` reused as topic-shift threshold — no new config variable
- `build_contextual_text()` for stored embeddings unchanged

### Context-Prepended Embeddings (v5.6.0)
- All messages embedded with conversational context via `build_contextual_text()`
  in `utils/embedding_context.py` (format: `[Context: a1: msg1 | ...]\nauthor: content`)
- Reply chains: replied-to message used as primary context
- Query embedding also contextual: last 3 in-memory conversation messages prepended
- `!debug reembed` + `!summary create` required after deploy to rebuild embeddings/clusters
- `utils/context_retrieval.py` — retrieval extracted from context_manager.py
- `commands/cluster_commands.py` — cluster commands extracted from debug_commands.py

### Noise Guard (v5.5.1)
- `raw_events.py` `_looks_like_diagnostic()` skips embedding bot-authored
  messages whose content starts with known diagnostic prefixes (`Cluster `,
  `Parameters:`, `Processed:`, `**Cluster Analysis`, etc.) — belt-and-suspenders
  against prefix loss; `debug_commands.py` v1.6.0 routes all pagination through
  `send_paginated()` to guarantee ℹ️ on every chunk

### Semantic Retrieval (v5.5.0 — cluster-based)
- Response path uses `find_relevant_clusters()` + `get_cluster_messages()` from
  `cluster_retrieval.py`
- `_retrieve_cluster_context()` in `context_manager.py` replaces `_retrieve_topic_context()`
- `[Topic: {label}]` section header preserved — model framing unchanged
- Fallback (`find_similar_messages`) still fires when no clusters pass threshold

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

### Persistence
- SQLite with WAL mode: messages, summaries, embeddings, clusters, cluster_messages
- Settings recovered from Discord message history on startup
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
