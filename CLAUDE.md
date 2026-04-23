# CLAUDE.md
# Version 7.3.1

This file provides guidance to Claude Code when working with this repository.

## Development Procedure

Every change follows this exact order. Steps marked ⛔ require explicit user approval before proceeding.

1. ⛔ **Discuss + get approval** — present problem, solution, alternatives; wait for "yes" before writing code
2. **Develop on `claude-code` branch** — never commit directly to `main` or `development`
3. **Implement** — 250-line limit, version bumps, docstring changelogs
4. ⛔ **Test via Discord commands** — report results; wait for approval before continuing
5. **Update docs + commit** — README.md, STATUS.md, HANDOFF.md, README_ENV.md, CLAUDE.md, AGENT.md in same commit as code; never push code without docs
6. ⛔ **Push to `claude-code`** — wait for approval before pushing
7. ⛔ **Merge to `development`** — wait for approval; never merge to `main`

## Running the Bot

```bash
pip install -r requirements.txt
python main.py                    # requires .env with DISCORD_TOKEN
LOG_LEVEL=DEBUG python main.py    # debug logging
```

No automated tests. Validation via Discord commands.

## Environment Setup

```bash
# Required
DISCORD_TOKEN=your_discord_bot_token
OPENAI_API_KEY=your_openai_key        # embeddings + classifier

# Conversation provider
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=your_deepseek_key
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-chat

# Summarization
SUMMARIZER_PROVIDER=gemini
SUMMARIZER_MODEL=gemini-3.1-flash-lite-preview
SUMMARIZER_BATCH_SIZE=500
GEMINI_API_KEY=your_gemini_key
GEMINI_MAX_TOKENS=32768

# Optional
DATABASE_PATH=./data/messages.db
CONTEXT_BUDGET_PERCENT=80
MAX_RECENT_MESSAGES=5
CONTROL_FILE_PATH=./data/control.txt  # injected into every system prompt
SESSION_GAP_MINUTES=30                # session boundary for session bridge
LAYER2_BUDGET_PCT=0.7                 # fraction of remaining budget for Layer 2
```

Priority: shell env vars > `.env` file > `config.py` defaults.

## Architecture

### Message Flow
1. `main.py` → loads .env, creates bot, runs with DISCORD_TOKEN
2. `bot.py` → on_message routes to response pipeline or commands
3. First message in channel triggers `load_channel_history()`:
   - `restore_settings_from_db()` — queries SQLite for ⚙️ bot messages → settings applied without Discord fetch
   - `_seed_history_from_db()` — last MAX_HISTORY×10 messages from SQLite, filtered → in-memory buffer
   - Delta Discord fetch (`after=last_processed_id`) — only messages newer than last DB record
4. Addressed messages → `build_context_for_provider()` → `handle_ai_response()`
5. `raw_events.py` → persists every message to SQLite + embeds with OpenAI in parallel

### Context Assembly (v7.0.0 — three-layer budget-priority)
Every response context has three layers assembled in priority order:

**Layer 1 (guaranteed):** System prompt + `data/control.txt` (if exists) +
always-on summary (overview, key facts, open actions, open questions).

**Layer 2 (guaranteed):** Session bridge + unsummarized messages, injected as
message turns. Budget-capped at `LAYER2_BUDGET_PCT=70%` of remaining after
Layer 1 — always wins over retrieval. Recent messages never trimmed for history.
- Session bridge: source messages from most recent session's non-clustered segments
  (walk backward until gap > `SESSION_GAP_MINUTES`; excludes `clustered/unclustered`
  which are already in Layer 1; includes `indexed` segments from the worker).
- Unsummarized: messages after the max message ID in any `clustered/unclustered`
  segment. Boundary moves only on `!summary create` — worker indexing does not drain it.

**Layer 3 (fills remainder):** Historical RRF retrieval (propositions + dense +
BM25) — same retrieval path as v6.4.x, now with `exclude_ids` to avoid
duplicating Layer 2 messages.

Retrieval path (`context_manager.py` → `context_retrieval.py`):
1. `embed_query_with_smart_context()` on contextual query
2. `find_relevant_propositions()` — cosine vs ALL proposition embeddings; collapse max-score-per-segment → seg IDs
3. `find_relevant_segments(top_k*2)` — cosine vs ALL segment embeddings, expanded pool
4. `_apply_score_gap()` — cuts dense candidates at largest inter-score gap ≥ 0.08
5. `fts_search(query_text)` — BM25 keyword search via SQLite FTS5
6. `rrf_fuse(prop, dense, bm25, k=RRF_K)` — Reciprocal Rank Fusion → final top-K IDs
7. `get_segment_with_messages()` — synthesis + source messages per segment; noise-filtered (skips ℹ️/⚙️, !commands)
8. Rollback: if no segments, `_cluster_rollback()` (in `cluster_fallback.py`) uses cluster centroids

**Embedding strategy (v5.6.0):**
All embeddings include conversational context via `build_contextual_text()` in
`utils/embedding_context.py`. Format: `[Context: a1: msg1 | a2: msg2]\nauthor: content`.
Reply chains: replied-to message used as primary context instead of sliding window.
After deploy: run `!debug reembed` + `!summary create` to rebuild with contextual embeddings.

**Smart query embedding (v5.6.1):**
Query uses `embed_query_with_smart_context()` to avoid topic bleed-through:
- Path 1: previous message was a question → embed with question as context
- Path 2: cosine-compare raw query to previous stored embedding; if `sim > QUERY_TOPIC_SHIFT_THRESHOLD`
  re-embed with context (same topic), else use raw (topic shift)
`build_contextual_text()` for stored embeddings is unchanged.

Fallback chain:
Fallback chain (Layer 3):
1. Segments above `RETRIEVAL_FLOOR` → inject as `[Topic: {label}]` with source messages
2. No segments → `_cluster_rollback()` — cluster centroids + `get_cluster_messages()`
3. No clusters → direct message embedding search
4. All empty → full summary injected + WARNING logged

Timestamps: every retrieved message prefixed with `[YYYY-MM-DD]`; today's date injected
at top of context block. Section header uses `[Topic: {label}]` — model-facing framing.

Citations (v5.9.0): retrieved messages numbered `[N]` contiguously across segments;
citation instruction injected into context block header; `apply_citations()` strips
hallucinations and builds Sources footer after response; footer sent as ℹ️ follow-up
if combined length > 1950 chars. No citations when retrieval empty or for commands.
Key files: `utils/citation_utils.py` (strip/build/apply), `utils/context_retrieval.py`
(citation numbering + 4-tuple return), `utils/context_manager.py` (citation pass-through)

Key files: `utils/pipeline_state.py` (pipeline CRUD, session bridge, unsummarized queries),
`utils/context_helpers.py` (Layer 2 helpers), `utils/cluster_fallback.py` (v5.x rollback),
`utils/cluster_retrieval.py` (find_relevant_segments, get_segment_with_messages),
`utils/fts_search.py` (populate_fts, fts_search, rrf_fuse), `utils/context_retrieval.py` (hybrid retrieval + fallback),
`utils/embedding_context.py` (build_contextual_text), `utils/context_manager.py` (three-layer assembly, v3.0.4),
`utils/segment_store.py` (segment CRUD + status), `utils/cluster_store.py` (cluster CRUD + status),
`utils/history/discord_loader.py` (DB seed + delta fetch), `utils/history/realtime_settings_parser.py` (restore_settings_from_db)

### Incremental Assignment (v5.4.0)
After embedding, `raw_events.py` calls `assign_to_nearest_cluster(channel_id, message_id)`
via `asyncio.to_thread`. If clusters exist and the best cosine score >= RETRIEVAL_MIN_SCORE,
the message is inserted into `cluster_messages` and the centroid updated (running average +
renormalize). The cluster is flagged `needs_resummarize=1`. Fails silently — no clusters is
not an error (bot may be in channels where `!summary create` has never run).

`!summary update` → `quick_update_channel()` → `run_quick_update()` in `cluster_update.py`:
re-summarizes dirty clusters via `summarize_cluster()`, marks clean, re-runs the full
post-processing stack (classify → overview → dedup → answered-Q → save). Preserves
`cluster_count` and `noise_message_count` from existing summary (no re-cluster).

Key files: `utils/cluster_assign.py` (centroid assignment), `utils/cluster_update.py` (quick pipeline), `utils/cluster_store.py` (dirty cluster CRUD), `schema/006.sql`

### Summarization Pipeline (v6.0.0 — segment-based)
`!summary create` runs the segment pipeline via `summarizer.py` v4.7.0:
```
summarize_channel(channel_id)                  ← summarizer.py
  → run_segmentation_phase()                   ← segmenter.py
      Gemini batch-processes messages (500/batch, 20 overlap)
      → topic boundaries + synthesis (resolves implicit refs)
      → store_segments() + embed syntheses     ← segment_store.py
  → run_segment_clustering()                   ← segment_store.py
      UMAP + HDBSCAN on segment embeddings
      store to clusters + cluster_segments (NOT cluster_messages)
  → run_cluster_pipeline(pre_run_stats=stats)  ← cluster_overview.py
      → summarize_all_clusters(use_segments=True) ← cluster_summarizer.py
          M-labeled segment syntheses → Gemini per cluster
      → _collect_structured_items()
      → classify_overview_items()              ← cluster_classifier.py
      → generate_overview()
      → deduplicate_summary()                  ← cluster_qa.py
      → remove_answered_questions()            ← cluster_qa.py
      → save_channel_summary()
```
Fallback: if segmentation yields 0 segments OR segment clustering fails,
falls back to direct message clustering (v5.x path) automatically.

Key files: `summarizer.py` (router), `segmenter.py` (Gemini segmentation+synthesis),
`segment_store.py` (CRUD + run_segment_clustering), `cluster_overview.py` (orchestrator),
`cluster_summarizer.py` (per-cluster Gemini), `cluster_classifier.py` (whitelist filter),
`cluster_qa.py` (dedup + answered-Q check), `cluster_engine.py` (UMAP + HDBSCAN)

**v4.x three-pass pipeline** was removed in v5.10.0 (git history preserves). Only the cluster/segment pipeline is active.

### Noise Filtering
All bot output prefixed with ℹ️ (noise) or ⚙️ (settings persistence).
Filters in `message_processing.py`: `is_noise_message()`, `is_settings_message()`.

Embedding noise filter (v5.13.0): `utils/embedding_noise_filter.py`
`should_skip_embedding(content, is_bot_author)` — single gate applied at
embed time (`raw_events.py`) and backfill (`embedding_store.py`). Skips
commands, bot output, diagnostic prefixes, `[Original Message Deleted]`
placeholders, and messages under 4 words (questions exempt).

### Providers
- OpenAI, Anthropic, DeepSeek (conversation) — per-channel configurable
- Gemini (summarization Secretary/Structurer) — not used for conversation
- OpenAI GPT-4o-mini (classifier) — always used regardless of conversation provider
- OpenAI text-embedding-3-small (embeddings) — always used
- All providers: singleton cached, async executor wrapped

### Persistence
- SQLite with WAL mode (`data/messages.db`)
- Tables: messages, summaries, message_embeddings, clusters, cluster_messages, segments, segment_messages, cluster_segments
- `raw_events.py` captures all messages including bot responses + embeds them
- `db_migration.py` applies `schema/NNN.sql` files sequentially
- Settings recovered from Discord history on startup

## Key Design Decisions

- **Decision = agreement on action** — "I think X" / "Agreed" → decision.
  "What is X?" / "X is Y" → fact, NOT a decision.
- **Fresh-from-source > recursive** — Gemini's 1M context sends raw messages directly
- **Prefix-based filtering** — single ℹ️/⚙️ check replaces 30+ patterns
- **Full budget for retrieval** — no pre-allocated slice; trimmer adjusts recent messages

## Commands Reference

| Command | Description |
|---------|-------------|
| `!summary` | Show channel summary |
| `!summary full` | All sections including key facts |
| `!summary create/clear` | Run summarization / delete (admin) |
| `!debug noise/cleanup/status` | Maintenance tools (admin) |
| `!debug backfill` | Embed missing messages + contextual text (admin) |
| `!debug segments` | Show segment count, avg size, sample syntheses (admin) |
| `!debug pipeline` | Show pipeline state — unsummarized count, last run, session bridge (admin) |
| `!pipeline status` | Show worker state, lock holder, unsegmented count, last run (admin) |
| `!pipeline stop` | Stop the background pipeline worker (admin) |
| `!pipeline start` | Start the background pipeline worker (admin) |
| `!pipeline run` | Run one manual pipeline cycle immediately (admin) |
| `!explain` | Context receipt for most recent bot response |
| `!explain detail` | Receipt + injected messages per cluster |
| `!explain <id>` | Context receipt for specific response message ID |
| `!explain detail <id>` | Detail view for specific response |
| `!status` | Bot settings for this channel |
| `!autorespond` | Auto-response toggle |
| `!ai` | AI provider switch |
| `!thinking` | DeepSeek thinking display |
| `!prompt` | System prompt management |
| `!history` | View/clean/reload history |

## Code Conventions

- 250-line file limit — extract to new module when exceeded
- All `ctx.send()` must use ℹ️ or ⚙️ prefix
- Version header + docstring changelog in every file
- `asyncio.to_thread()` for all SQLite operations
- `run_in_executor()` for all provider API calls
