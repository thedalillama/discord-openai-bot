# CLAUDE.md
# Version 5.8.0

This file provides guidance to Claude Code when working with this repository.

## Workflow Rules

- **NO CODE CHANGES WITHOUT APPROVAL** — discuss first, wait for approval
- **Always present complete files** — never partial diffs or patches
- **Increment version numbers** — bump header and update docstring changelog
- **Update README.md, STATUS.md, HANDOFF.md, README_ENV.md** alongside every code change
- **All development in `development` or feature branches** — `main` is production

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
```

Priority: shell env vars > `.env` file > `config.py` defaults.

## Architecture

### Message Flow
1. `main.py` → loads .env, creates bot, runs with DISCORD_TOKEN
2. `bot.py` → on_message routes to response pipeline or commands
3. First message in channel triggers `load_channel_history()` backfill
4. Addressed messages → `build_context_for_provider()` → `handle_ai_response()`
5. `raw_events.py` → persists every message to SQLite + embeds with OpenAI in parallel

### Semantic Retrieval (v5.6.0 — contextual cluster-based)
Every response context has two layers:
- **Always-on**: overview, key facts, open actions, open questions (from summary)
- **Retrieved**: latest user message embedded WITH context → top cluster centroids →
  cluster member messages injected as "PAST MESSAGES FROM THIS CHANNEL"

Retrieval path (`context_manager.py` → `context_retrieval.py`):
1. Build contextual query: prepend last 3 in-memory conversation messages
2. `embed_text()` on contextual query
3. `find_relevant_clusters()` — cosine similarity vs cluster centroids, top-K
4. Filter by `RETRIEVAL_MIN_SCORE` (0.25 default; 0.45 in production .env)
5. `get_cluster_messages()` — direct member messages, exclude recent_ids

**Embedding strategy (v5.6.0):**
All embeddings include conversational context via `build_contextual_text()` in
`utils/embedding_context.py`. Format: `[Context: a1: msg1 | a2: msg2]\nauthor: content`.
Reply chains: replied-to message used as primary context instead of sliding window.
After deploy: run `!debug reembed` + `!summary create` to rebuild with contextual embeddings.

**Smart query embedding (v5.6.1):**
Query uses `embed_query_with_smart_context()` to avoid topic bleed-through:
- Path 1: previous message was a question → embed with question as context
- Path 2: cosine-compare raw query to previous stored embedding; if `sim > RETRIEVAL_MIN_SCORE`
  re-embed with context (same topic), else use raw (topic shift)
`build_contextual_text()` for stored embeddings is unchanged.

Fallback chain:
1. Clusters above `RETRIEVAL_MIN_SCORE` with messages → inject as `[Topic: {label}]`
2. No clusters above threshold OR all clusters have 0 messages → direct message search
3. Both empty (no clusters, no embeddings) → full summary injected + WARNING logged

Timestamps: every retrieved message prefixed with `[YYYY-MM-DD]`; today's date injected
at top of context block. Section header uses `[Topic: {label}]` — model-facing framing.

Key files: `utils/cluster_retrieval.py` (find_relevant_clusters, get_cluster_messages),
`utils/context_retrieval.py` (retrieval + fallback, extracted v5.6.0),
`utils/embedding_context.py` (build_contextual_text, v5.6.0),
`utils/context_manager.py` (always-on + budget + timestamps)

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

Key files: `utils/cluster_assign.py` (centroid assignment), `utils/cluster_update.py`
(quick pipeline), `utils/cluster_store.py` (dirty cluster CRUD), `schema/006.sql`

### Summarization Pipeline (v5.3.0 — cluster-based)
`!summary create` runs the full cluster pipeline via `summarizer.py` v3.0.0:
```
run_cluster_pipeline(channel_id)               ← cluster_overview.py
  → UMAP + HDBSCAN clustering                  ← cluster_engine.py
  → summarize_all_clusters()                    ← cluster_summarizer.py
      M-labeled messages → Gemini per cluster
      store label + summary JSON blob + status
  → _collect_structured_items()
      aggregate decisions/facts/actions/questions from all cluster blobs
  → classify_overview_items()                   ← cluster_classifier.py
      GPT-4o-mini whitelist filter, default-to-DROP
  → generate_overview()
      Gemini: labels + summary texts only → overview + participants
  → merge overview + participants + filtered items
  → translate_to_channel_summary()
      text → fact/task/question/decision (v4.x field names)
  → deduplicate_summary()                       ← cluster_qa.py
      embedding cosine dedup, 0.85 threshold
  → remove_answered_questions()                 ← cluster_qa.py
      GPT-4o-mini YES/NO per question vs decisions + facts
  → save_channel_summary() → channel_summaries table
```

Key files: `summarizer.py` (router), `cluster_overview.py` (orchestrator + overview LLM),
`cluster_summarizer.py` (per-cluster Gemini), `cluster_classifier.py` (whitelist filter),
`cluster_qa.py` (dedup + answered-Q check), `cluster_engine.py` (UMAP + HDBSCAN),
`cluster_store.py` (CRUD)

**v4.x three-pass pipeline** (`summarizer_authoring.py` etc.) is retained but
no longer called — rollback safety only.

### Noise Filtering
All bot output prefixed with ℹ️ (noise) or ⚙️ (settings persistence).
Filters in `message_processing.py`: `is_noise_message()`, `is_settings_message()`.

### Providers
- OpenAI, Anthropic, DeepSeek (conversation) — per-channel configurable
- Gemini (summarization Secretary/Structurer) — not used for conversation
- OpenAI GPT-4o-mini (classifier) — always used regardless of conversation provider
- OpenAI text-embedding-3-small (embeddings) — always used
- All providers: singleton cached, async executor wrapped

### Persistence
- SQLite with WAL mode (`data/messages.db`)
- Tables: messages, summaries, message_embeddings, topics, topic_messages
- `raw_events.py` captures all messages including bot responses + embeds them
- `db_migration.py` applies `schema/NNN.sql` files sequentially
- Settings recovered from Discord history on startup

## Key Design Decisions

- **Decision = agreement on action** — "I think X" / "Agreed" → decision.
  "What is X?" / "X is Y" → fact, NOT a decision.
- **Fresh-from-source > recursive** — Gemini's 1M context sends raw messages directly
- **Secretary writes freely** — no JSON constraint in Pass 1
- **Prefix-based filtering** — single ℹ️/⚙️ check replaces 30+ patterns
- **Hash protection** — SHA-256 on protected fields, supersession lifecycle
- **Threshold-based linking** — all messages above score threshold linked to topic, not top-N
- **Full budget for retrieval** — no pre-allocated slice; trimmer adjusts recent messages

## Commands Reference

| Command | Description |
|---------|-------------|
| `!summary` | Show channel summary |
| `!summary full/raw` | Full view / Secretary's raw minutes |
| `!summary create/clear` | Run summarization / delete (admin) |
| `!debug noise/cleanup/status` | Maintenance tools (admin) |
| `!debug backfill` | Embed missing messages + re-link all topics (admin) |
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
