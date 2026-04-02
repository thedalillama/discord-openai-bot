# HANDOFF.md
# Version 5.5.0
# Agent Development Handoff Document

## Current Status

**Branch**: claude-code
**Bot version**: v5.5.0
**Bot**: Running on GCP VM as systemd service (`discord-bot`)
**Main branch**: tagged v4.0.0
**Pipeline**: cluster-v5 fully live (clustering + incremental assignment + cluster retrieval)

---

## What Just Happened

### v5.5.0 — Cluster-Based Retrieval Integration

Swapped topic-based retrieval for cluster-based retrieval in the response path.
The full v5 architecture is now live end-to-end.

**New file:**
- `utils/cluster_retrieval.py` v1.0.0 — `find_relevant_clusters()` (cosine similarity
  vs cluster centroids, returns top-K `(cluster_id, label, score)`) and
  `get_cluster_messages()` (member messages with `exclude_ids` dedup)

**Modified file:**
- `utils/context_manager.py` v2.2.0 — `_retrieve_topic_context()` renamed to
  `_retrieve_cluster_context()`; imports and calls swapped to cluster functions;
  `[Topic: {label}]` framing, fallback path, token budget, timestamps unchanged

**Why `cluster_retrieval.py` instead of `cluster_store.py`:**
`cluster_store.py` was at the 250-line limit. Retrieval (query-time scoring) is
also semantically separate from CRUD (write/read operations).

**Retained for rollback:** `find_relevant_topics()`, `get_topic_messages()` in
`embedding_store.py` — untouched, just no longer called.

---

### v5.4.0 — Incremental Cluster Assignment + `!summary update`

New messages are now automatically assigned to the nearest cluster centroid on
arrival (Tier 1), and `!summary update` re-summarizes only the affected clusters
without re-running UMAP + HDBSCAN (Tier 2). Full rebuild via `!summary create`
remains Tier 3.

**New files:**
- `schema/006.sql` — `ALTER TABLE clusters ADD COLUMN needs_resummarize INTEGER DEFAULT 0`
- `utils/cluster_assign.py` v1.0.0 — synchronous `assign_to_nearest_cluster(channel_id, message_id)`:
  loads embedding from `message_embeddings`, finds best centroid match above RETRIEVAL_MIN_SCORE,
  updates centroid via running average + renormalize, inserts into `cluster_messages`, sets
  `needs_resummarize=1`
- `utils/cluster_update.py` v1.0.0 — `run_quick_update(channel_id, provider, progress_fn)`:
  loads dirty clusters, re-summarizes each via `summarize_cluster()`, marks clean, re-runs
  classify → overview → dedup → answered-Q → save; preserves `cluster_count` + `noise_message_count`

**Modified files:**
- `utils/cluster_store.py` v2.0.0 — `get_dirty_clusters()`, `mark_clusters_clean()`,
  `get_unassigned_message_count()`
- `utils/raw_events.py` v1.4.0 — after embedding, calls `assign_to_nearest_cluster` via
  `asyncio.to_thread`; fails silently (DEBUG log only)
- `utils/summarizer.py` v3.1.0 — `quick_update_channel()` thin router
- `commands/summary_commands.py` v2.4.0 — `!summary update` subcommand

**Key design decisions:**
- No message is silently dropped — unassigned messages are counted and reported with
  a prompt to run `!summary create` when the count is significant
- Centroid update uses running average so cluster shape degrades gracefully with new messages
- `cluster_update.py` imports `_collect_structured_items` and `translate_to_channel_summary`
  directly from `cluster_overview.py` (private by convention, but accessed cross-module)
- `cluster_count` + `noise_message_count` preserved from existing summary — no re-cluster,
  so those stats haven't changed

**Result format from `quick_update_channel()`:**
```python
{
    "updated_count": 3,      # clusters re-summarized
    "unassigned_count": 12,  # embedded messages not in any cluster
    "overview_generated": True,
    "error": None,
    "message": "OK",
}
```

---

### v5.3.0 — Cluster Pipeline (validated + committed)

`!summary create` now runs the full cluster-v5 pipeline. The v4.x three-pass
Secretary/Structurer/Classifier pipeline is no longer called (retained for rollback).

**Pipeline order:**
```
1. UMAP + HDBSCAN  →  cluster_engine.py
2. Per-cluster Gemini summarize  →  cluster_summarizer.py
3. Aggregate structured items from all cluster blobs
4. GPT-4o-mini classifier (whitelist, default-to-DROP)  →  cluster_classifier.py
5. Overview Gemini (labels + summaries only → overview + participants)  →  cluster_overview.py
6. Merge overview + participants + filtered items
7. translate_to_channel_summary() (text → fact/task/question/decision)
8. Embedding dedup (0.85 cosine threshold)  →  cluster_qa.py
9. Answered-Q check (GPT-4o-mini YES/NO)  →  cluster_qa.py
10. save_channel_summary()
```

**Key decisions made during development:**
- Classifier runs BEFORE overview LLM — original design sent all structured fields to Gemini,
  producing 16K+ token output that truncated and failed to parse with 56 clusters
- Overview LLM receives labels + summary texts only — reduces output to a few hundred tokens
- GPT-4o-mini and DeepSeek Reasoner both failed at full-JSON QA dedup — LLMs won't delete
  content they're given; embedding dedup solves this without LLM reluctance
- Default-to-DROP on missing classifier verdicts — truncated responses produce less noise

**New files:**
- `utils/cluster_overview.py` v2.2.0
- `utils/cluster_classifier.py` v1.6.0
- `utils/cluster_qa.py` v1.0.0

**Modified files:**
- `utils/summarizer.py` v3.0.0 — thin router to `run_cluster_pipeline()`
- `commands/summary_commands.py` v2.3.0 — cluster-v5 stats display; clear clusters on clear
- `utils/summary_display.py` v1.3.2 — footer shows `N clusters (M noise) | cluster-v5`

**Result format from `summarize_channel()` (v5 path):**
```python
{
    "cluster_count": 56,
    "noise_count": 12,
    "messages_processed": 741,
    "overview_generated": True,
    "error": None,
}
```

**Known issues (minor):**
- A few near-duplicate key facts survive dedup (e.g. age phrased two different ways with
  cosine similarity just under 0.85) — acceptable for now
- One stale action item (flight check for a past date) — classifier correctly KEEPs it
  because it has a human owner, but the QA answered-Q check doesn't catch stale dates
- Both are cosmetic and don't affect bot response quality

**What's next (v5.4.0):** Swap topic retrieval (`find_relevant_topics()`) with cluster
centroid retrieval — use cluster centroids instead of topic embeddings for the per-query
context injection path.

---

### v5.2.0 — Per-Cluster LLM Summarization

Phase 2 of the v5 cluster-based summarization pipeline. Each cluster now
gets a structured LLM summary (label, summary, decisions, key_facts,
action_items, open_questions, status) via a single Gemini call per cluster.

**New files:**
- `utils/cluster_summarizer.py` v1.0.0 — `CLUSTER_SYSTEM_PROMPT`,
  `CLUSTER_SUMMARY_SCHEMA` (flat JSON, summary field listed first to force
  synthesis before extraction); `summarize_cluster()` loads messages, formats
  with M-labels (M1, M2, ...), truncates to 50 most recent if cluster > 50
  msgs, calls Gemini with structured output, retries once on failure, stores
  label/summary JSON blob/status; `summarize_all_clusters()` sequential loop
  returning `{processed, failed}` counts

**Modified files:**
- `utils/cluster_store.py` v1.1.0 — added four helpers:
  `get_cluster_message_ids()`, `get_clusters_for_channel()`,
  `update_cluster_label_summary()`, `get_messages_by_ids()` (added here
  instead of message_store.py which is at 254 lines)
- `commands/debug_commands.py` v1.5.0 — `!debug summarize_clusters` command:
  checks for existing clusters (prompts `!debug clusters` if none), iterates
  clusters calling `summarize_cluster()` per cluster, sends Discord progress
  every 5 clusters, paginates final report

**Summary JSON blob format** (stored in `clusters.summary`):
```json
{
    "text": "1-3 sentence summary...",
    "decisions": [...],
    "key_facts": [...],
    "action_items": [...],
    "open_questions": [...]
}
```

**To validate:**
1. Run `!debug summarize_clusters` on #openclaw (56 clusters → 1-3 min, ~56 Gemini calls)
2. Verify labels are 3-8 words and descriptive
3. Verify `clusters.summary` is populated: `SELECT id, label, summary FROM clusters LIMIT 5`
4. Check failure count in output — expect 0 failures
5. Verify existing bot behavior unchanged (regression check)

**What's next (Phase 3):** Cross-cluster overview + summary storage — generates
channel-level overview from cluster summaries, stores in `channel_summaries`,
wires into `!summary create` to replace the v4.x three-pass pipeline.

---

### v5.1.0 — Schema + HDBSCAN Clustering Core

Phase 1 of the v5 cluster-based summarization pipeline. No LLM calls,
no changes to the response pipeline. Proves that clustering produces
meaningful topic groups from existing message embeddings.

**New files:**
- `schema/005.sql` — `clusters` + `cluster_messages` tables; migration
  applied automatically on restart
- `utils/cluster_engine.py` v1.0.0 — UMAP (cosine, 1536→5 dims) +
  HDBSCAN (euclidean, eom selection); noise reduction reassigns noise
  points to nearest centroid above RETRIEVAL_MIN_SCORE (0.25); centroids
  computed as normalized mean in original 1536-dim space
- `utils/cluster_store.py` v1.0.0 — SQLite CRUD, run_clustering()
  orchestrator, format_cluster_report() for Discord output

**Modified files:**
- `config.py` v1.13.0 — CLUSTER_MIN_CLUSTER_SIZE, CLUSTER_MIN_SAMPLES,
  UMAP_N_NEIGHBORS, UMAP_N_COMPONENTS (all env-var overridable)
- `debug_commands.py` v1.4.0 — `!debug clusters` runs pipeline, stores
  results, displays report
- `requirements.txt` — scikit-learn>=1.3, umap-learn>=0.5

**To validate:**
1. Run `!debug clusters` on #openclaw — expect 8-15 clusters, <30% noise
2. Run on large channel (~1600 msgs) — expect <10s, 15-40 clusters
3. Spot-check coherence by querying cluster_messages JOIN messages

**What's next (Phase 2):** Per-cluster LLM summarization — reads
`clusters` + `cluster_messages`, calls Gemini Flash Lite for each
cluster, populates `clusters.label` and `clusters.summary`.

---

### v4.1.10 — Inject Today's Date into Context
The model had no way to know the current date, so retrieved message timestamps
like `[2025-03-01]` were uninterpretable without a reference point.

**Fix**: `date.today().isoformat()` injected as `Today's date: YYYY-MM-DD` at
the top of the `--- CONVERSATION CONTEXT ---` block. Applied to both the normal
retrieved path and the full-summary fallback path.

**Files changed**: `context_manager.py` v2.1.5

### v4.1.9 — Timestamps on Retrieved Messages
Retrieved messages had no date context, making old and new discussions
indistinguishable to the model.

**Fix**: Each retrieved message line is now prefixed with `[YYYY-MM-DD]`
extracted from `created_at`. Applied in both `_retrieve_topic_context()` (topic
path) and `_fallback_msg_search()` (direct message fallback path).
`find_similar_messages()` updated to return `created_at` as the 4th tuple
element — score is now internal-only, used for sort before being stripped.
`get_topic_messages()` already returned `created_at`; no change needed there.

**Files changed**: `embedding_store.py` v1.7.0, `context_manager.py` v2.1.4

### v4.1.8 — Batched Cold Start
Cold start was passing all messages to `cold_start_pipeline()` at once.
For channels with 750+ messages this produced a 65K+ token Structurer response.
The `batch_size` parameter accepted by `cold_start_pipeline()` was never used.

**Fix**: `summarize_channel()` now slices `all_messages[:effective_batch]` before
calling `cold_start_pipeline()`. If messages remain, it re-reads the saved summary
from DB and feeds the rest through `_incremental_loop()` (which already handles
batching correctly). Combined result returned to caller.

**Files changed**: `summarizer.py` v2.2.0

**To verify**: Run `!summary clear` + `!summary create` on a channel with >500
messages. Logs should show "Cold start: 500 of N msgs" followed by incremental
batches. No 65K+ token Structurer responses.

### v4.1.7 — Batch Embedding Backfill
`!debug backfill` was embedding one message at a time — 1,600 sequential API
calls for a channel with 1,600 messages. OpenAI's embeddings endpoint accepts
up to 2,048 inputs per call.

**Fix**: Added `embed_texts_batch(texts, batch_size=1000)` to `embedding_store.py`.
Collects all pending message texts, calls the API once per 1000 messages, logs
per-batch success/failure counts and total elapsed time.

**Bug fix**: Re-link phase previously only processed `active_topics`. Updated to
include `archived_topics`, matching `summarizer_authoring.py` behaviour.

**Files changed**: `embedding_store.py` v1.6.0, `debug_commands.py` v1.3.0

**To verify**: Run `!debug backfill` on a channel with many unembedded messages.
Should complete in seconds rather than minutes; log shows per-batch counts; Discord
reports elapsed time.

### v4.1.6 — Restore Always-On Context Injection
Always-on was suppressed during testing. Restored now that the topic list is clean
and the key facts label reads "Key facts established in this conversation:".
Covers personal/project facts (age, favorite number, database, hosting, rate limit)
that aren't in any topic and can't be reached via retrieval alone.

**Files changed**: `context_manager.py` v2.1.3

### v4.1.5 — Full Summary Fallback as Warning
Branch 4 (no topics + no message embeddings) was logging at DEBUG, making
degraded retrieval state invisible. Changed to WARNING so monitoring catches it.

**Files changed**: `context_manager.py` v2.1.2

### v4.1.4 — Secretary Prompt: Ignore Bot Noise (Fix 1B)
Prevents bot-noise topics from being created at summarization time. The Secretary
was previously recording bot self-descriptions, capability statements, and
conversational filler as topics — these then polluted retrieval.

**Fix**: Added IGNORE section to `SECRETARY_SYSTEM_PROMPT` listing what to omit:
generic self-descriptions, capability statements, diagnostic responses, filler.
Combined with Fix 1A, noise topics should not appear in retrieval even if
they somehow get created.

**Files changed**: `summary_prompts_authoring.py` v1.6.0

**To verify**: Run `!summary clear` + `!summary create` — topic list should
contain no "Bot ..." entries.

### v4.1.3 — Noise Topic Filter (Fix 1A)
Bot-noise topics ("Bot self-descriptions", "Bot capability tests", etc.) were
scoring high against many queries and consuming retrieval budget before relevant
content topics could be injected.

**Fix**: `_is_noise_topic()` added to `embedding_store.py` with `_NOISE_PATTERNS`
tuple. `find_relevant_topics()` partitions candidates into noise/content before
scoring — noise topics never enter the scored list. Filtered topics logged at DEBUG.

**Files changed**: `embedding_store.py` v1.5.0

### v4.1.2 — Topic Deduplication (Fix 2A)
Root cause: each `!summary create` upserted topics by ID but never deleted old ones.
35 topics accumulated for one channel — ~10 duplicates splitting relevant messages
across near-identical topics and inflating retrieval noise.

**Fix**: `clear_channel_topics()` added to `embedding_store.py`. Called in
`summarizer_authoring.py` before the topic storage loop — deletes all existing
topics + topic_messages for the channel, then inserts the fresh authoritative set.

**Files changed**: `embedding_store.py` v1.4.0, `summarizer_authoring.py` v1.10.2

**Next**: Run `!summary clear` + `!summary create` on test channel, verify topic
count drops from 35 to ~10-15 with no duplicates.

### v4.1.1 — Key Facts Framing Fix
Always-on key facts were labelled "Key facts:" without stating they came from the
conversation. The model treated them as background knowledge, answering "we haven't
discussed X" even when X appeared in key facts.

**Fix**: Changed label in `format_always_on_context()` to
`"Key facts established in this conversation:"` — matching the explicit framing
already used for the retrieved-messages section.

**Files changed**: `summary_display.py` v1.3.1

### v4.1.0 — Direct Message Embedding Fallback (PENDING DEPLOY)
When topic retrieval returns empty (no topics above RETRIEVAL_MIN_SCORE, or all
matched topics have 0 linked messages), `_retrieve_topic_context()` now falls
back to direct cosine similarity search across all `message_embeddings`.

**New function**: `find_similar_messages()` in `embedding_store.py` — queries
`message_embeddings` joined with `messages`, scores each against the query vector,
filters noise/commands, returns top-N sorted by score.

**New helper**: `_fallback_msg_search()` in `context_manager.py` — calls
`find_similar_messages()`, trims results to fit token budget, returns formatted
section `[Retrieved by message similarity]`.

**Two call sites** in `_retrieve_topic_context()`:
1. After topic threshold filter returns empty list
2. After topic loop produces no usable messages

`recent_ids` moved before the threshold filter so it's available at both sites.

**Files changed**: `embedding_store.py` v1.3.0, `context_manager.py` v2.1.0,
`config.py` v1.12.6 (RETRIEVAL_MSG_FALLBACK default 15)

### v4.0.0 — Topic-Based Semantic Retrieval (DEPLOYED + TESTED)
Replaces full summary injection with relevance-based context retrieval.

**Write path**:
- Messages embedded on arrival via OpenAI `text-embedding-3-small`
- Topics (active + archived) stored as first-class SQLite entities after every `!summary create`
- Each topic linked to ALL messages above `TOPIC_LINK_MIN_SCORE` (default 0.3) by cosine similarity

**Read path**:
- Always-on context: overview + key facts + open actions + open questions
- Per-query retrieval: embed latest user message → filter topics above RETRIEVAL_MIN_SCORE (0.3)
  → inject their linked messages; framed explicitly as real past messages from this channel
- Recent messages capped at 5 (MAX_RECENT_MESSAGES) to avoid overwhelming retrieved context
- Fallback: full summary injection if no topics pass threshold or embedding fails

**New files**: `utils/embedding_store.py` v1.2.0, `schema/004.sql`
**Modified**: `raw_events.py` v1.3.0, `summarizer_authoring.py` v1.10.1,
  `summary_display.py` v1.3.0, `context_manager.py` v2.0.4,
  `config.py` v1.12.5, `debug_commands.py` v1.2.0

**Test results** (#openclaw):
- Gorilla strength, diet (vegetarian), bachelor party toast — all retrieved correctly
- Common ancestor / DNA similarity — retrieved correctly
- Bonobos + chimps as human relatives — retrieved correctly
- Unrelated topics (aerodynamics) filtered by similarity threshold
- Incremental summarization: 44 new messages → 12 topics stored

**Known limitation**: Short exchanges (2–3 messages) that don't get captured as a
Structurer topic remain orphaned and invisible to retrieval. Planned for v4.1.0.

---

## Architecture Overview

### Semantic Retrieval Flow
```
Incoming user message
  → embed_text() (OpenAI text-embedding-3-small)
  → find_relevant_topics() (cosine similarity vs topic embeddings)
  → filter by RETRIEVAL_MIN_SCORE (0.3)
  → get_topic_messages() for each passing topic
  → inject as "PAST MESSAGES FROM THIS CHANNEL" in system prompt
  → token budget trimmer drops oldest recent messages to compensate
```

### Cluster-v5 Summarization Pipeline (current)
```
Message embeddings (already stored by raw_events.py)
  → UMAP (1536→5 dims, cosine) + HDBSCAN (euclidean, eom)
  → noise reassignment to nearest centroid
  → Per-cluster Gemini: label + summary + decisions + key_facts + action_items + open_questions
  → Aggregate all structured items (flat lists, fresh IDs)
  → GPT-4o-mini classifier: whitelist filter, default-to-DROP
  → Overview Gemini: labels + summary texts → overview + participants
  → Merge + translate_to_channel_summary() (text→fact/task/question/decision)
  → Embedding dedup (0.85 cosine) + answered-Q check (GPT-4o-mini YES/NO)
  → save_channel_summary()
```

### Three-Pass Summarization Pipeline (v4.x — retained for rollback)
```
Raw messages + existing minutes
  → Secretary (Gemini, natural language minutes)
  → Structurer (Gemini, anyOf JSON schema, camelCase ops)
  → translate_ops() (camelCase → snake_case)
  → Classifier (GPT-4o-mini, KEEP/DROP/RECLASSIFY, dedup vs existing)
  → apply_ops() → verify hashes → save
  → store_topic() + link_topic_to_messages() for all active + archived topics
```

### Token Budget Formula
```python
budget = int(context_window * CONTEXT_BUDGET_PERCENT / 100) - max_output_tokens
retrieval_budget = budget - system_base_tokens - always_on_tokens
# Retrieved content injected into system prompt
# system_tokens recalculated after injection
# recent messages trimmed to MAX_RECENT_MESSAGES and remaining token budget
```

### Schemas
- `STRUCTURER_SCHEMA` in `summary_delta_schema.py` — anyOf discriminated union, camelCase enums
- `DELTA_SCHEMA` in `summary_schema.py` — retained for `_process_response()` repair calls

### Diagnostic Files
Each pipeline run saves to `data/`:
- `secretary_raw_{channel_id}.txt` — Secretary output
- `structurer_raw_{channel_id}.json` — Structurer delta ops (after translate)
- `classifier_raw_{channel_id}.json` — kept IDs + dropped items

---

## Immediate Next Steps

### 1. Validate v5.5.0 on server
- Restart bot, ask questions about known cluster topics
- Check logs: `sudo journalctl -u discord-bot --since "1 min ago" | grep -i "cluster\|retrieved\|score"`
- Verify cluster label appears in logs, correct messages injected
- Ask about something never discussed — verify fallback fires, no error

### 2. Merge claude-code → main
v5.3.0, v5.4.0, and v5.5.0 are all implemented and ready.

---

## File Versions

### Semantic Retrieval Files (v4.1.0)
| File | Version | Key Role |
|------|---------|----------|
| `utils/embedding_store.py` | v1.3.0 | OpenAI embeddings, topic linking, direct fallback search |
| `utils/context_manager.py` | v2.1.0 | Always-on + retrieval + fallback, budget, 5-msg cap |
| `utils/summary_display.py` | v1.3.1 | format_always_on_context() — key facts framing fix |
| `utils/embedding_store.py` | v1.5.0 | clear_channel_topics() + _is_noise_topic() filter |
| `utils/summary_prompts_authoring.py` | v1.6.0 | IGNORE section in SECRETARY_SYSTEM_PROMPT |
| `utils/summarizer_authoring.py` | v1.10.2 | calls clear_channel_topics() before topic loop |
| `utils/raw_events.py` | v1.3.0 | Embed on arrival |
| `utils/summarizer_authoring.py` | v1.10.1 | Store active + archived topics |
| `commands/debug_commands.py` | v1.2.0 | !debug backfill |
| `config.py` | v1.12.6 | All retrieval config vars incl. RETRIEVAL_MSG_FALLBACK |
| `schema/004.sql` | — | topics, topic_messages, message_embeddings |

### Cluster Pipeline Files (v5.4.0)
| File | Version | Key Role |
|------|---------|----------|
| `utils/cluster_engine.py` | v1.0.0 | UMAP + HDBSCAN, noise reduction, centroids |
| `utils/cluster_store.py` | v2.0.0 | CRUD, run_clustering(), dirty cluster helpers |
| `utils/cluster_summarizer.py` | v1.0.0 | Per-cluster Gemini summarization |
| `utils/cluster_overview.py` | v2.2.0 | Pipeline orchestrator, overview LLM, field translation |
| `utils/cluster_classifier.py` | v1.6.0 | GPT-4o-mini whitelist filter |
| `utils/cluster_qa.py` | v1.0.0 | Embedding dedup + answered-Q check |
| `utils/cluster_assign.py` | v1.0.0 | On-arrival centroid assignment |
| `utils/cluster_update.py` | v1.0.0 | Quick re-summarization of dirty clusters |
| `utils/cluster_retrieval.py` | v1.0.0 | Query-time cluster retrieval |
| `utils/summarizer.py` | v3.1.0 | Routes !summary create + !summary update |
| `utils/raw_events.py` | v1.4.0 | Embed + assign to cluster on arrival |
| `utils/context_manager.py` | v2.2.0 | Cluster retrieval replaces topic retrieval |
| `utils/summary_display.py` | v1.3.2 | cluster-v5 footer + always-on formatter |
| `schema/005.sql` | — | clusters + cluster_messages tables |
| `schema/006.sql` | — | needs_resummarize column |

### v4.x Pipeline Files (retained for rollback)
| File | Version | Key Role |
|------|---------|----------|
| `utils/summarizer_authoring.py` | v1.10.2 | Three-pass Secretary/Structurer/Classifier |
| `utils/summary_delta_schema.py` | v1.0.0 | anyOf schema + translate_ops() |
| `utils/summary_classifier.py` | v1.3.0 | GPT-4o-mini + existing dedup |
| `utils/summary_prompts_authoring.py` | v1.6.0 | Secretary/Structurer prompts |
| `utils/summary_schema.py` | v1.4.0 | apply_ops(), verify, DELTA_SCHEMA |
| `utils/summary_store.py` | v1.1.0 | SQLite read/write |

---

## Known Issues

### 1. Orphaned Messages
Short exchanges that don't become Structurer topics are invisible to retrieval.
Example: 3 messages about the movie "Hamnet" — no topic created, no linkage,
bot answers from training knowledge instead of conversation history.

### 2. _build_existing_items() Missing pinned_memory
Classifier dedup doesn't check pinned_memory. Low priority — rarely used.

### 3. config.py Default SUMMARIZER_MODEL
Default `gemini-2.5-flash-lite` is stale. Server runs
`gemini-3.1-flash-lite-preview` via .env.

### 4. WAL File Stats Bug
`get_database_stats()` reports 0.0 MB — only measures main file, not WAL.

---

## .env Configuration (server)
```
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=sk-[key]
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-reasoner
SUMMARIZER_PROVIDER=gemini
SUMMARIZER_MODEL=gemini-3.1-flash-lite-preview
SUMMARIZER_BATCH_SIZE=500
GEMINI_API_KEY=[key]
GEMINI_MAX_TOKENS=32768
OPENAI_API_KEY=[key]   # Required for embeddings (text-embedding-3-small) + classifier
```

---

## Roadmap

| Milestone | Status |
|-----------|--------|
| M0-M3 | ✅ Complete |
| M3.5 anyOf schema | ✅ Complete (v3.5.0) |
| M3.5 pipeline unification | ✅ Complete (v3.5.1) |
| M3.5 classifier dedup | ✅ Complete (v3.5.1) |
| M3.5 overview inflation fix | ✅ Complete (v3.5.2) |
| M4 Topic-based semantic retrieval | ✅ Complete (v4.0.0) |
| M4.1 Direct message fallback retrieval | 🔄 Pending deploy (v4.1.0) |
| M4.1.1 Key facts framing fix | 🔄 Pending deploy (v4.1.1) |
| M4.1.2 Topic deduplication (Fix 2A) | 🔄 Pending deploy (v4.1.2) |
| M4.1.3 Noise topic filter (Fix 1A) | 🔄 Pending deploy (v4.1.3) |
| M4.1.4 Secretary prompt: ignore bot noise (Fix 1B) | 🔄 Pending deploy (v4.1.4) |
| M4.1.5 Full summary fallback as WARNING | 🔄 Pending deploy (v4.1.5) |
| M4.1.6 Restore always-on context | 🔄 Pending deploy (v4.1.6) |
| M5 Explainability | Planned |
| M6 Citation-backed generation | Planned |
| M7 Epoch compression | Planned |

---

## Development Rules
1. NO CODE CHANGES WITHOUT APPROVAL
2. Discuss before coding
3. ALWAYS provide full files — no partial patches
4. INCREMENT version numbers in file heading comments
5. Keep files under 250 lines
6. **Update README.md, STATUS.md, and HANDOFF.md with every commit**
7. Separate logical commits per change
