# STATUS.md
# Discord Bot Development Status
# Version 5.8.1

## Current Version Features

### Version 5.8.1 — Duplicate Test Message Cleanup

`!debug dedup` scans a channel for messages appearing 3+ times
(identical content) — typical of development testing. Shows a preview
of what will be removed. `!debug dedup confirm` executes:

- Soft-deletes duplicate messages (`is_deleted=1` — oldest copy kept)
- Hard-deletes their embeddings from `message_embeddings`
- Hard-deletes their cluster memberships from `cluster_messages`
- Marks affected clusters `needs_resummarize=1`

Note: the SOW named this `!debug cleanup` but that name was already taken
by the Discord noise-deletion command. `dedup` is more accurate.

**New files:**
- `commands/dedup_commands.py` v1.0.0

**Modified files:**
- `commands/debug_commands.py` v1.8.0 — updated help text
- `commands/__init__.py` v2.7.0 — registers dedup_commands

---

### Version 5.8.0 — Topic-Boundary-Aware Context Prepending

Fixes cross-topic contamination in stored embeddings. Previously
`build_contextual_text()` blindly prepended the 3 prior messages regardless
of topic. Redis questions got embedded with gorilla context; HDBSCAN then
placed them in the gorilla cluster.

**Fix:** before prepending, embed the current message raw and compute cosine
similarity against each previous message's stored embedding. Only same-topic
predecessors (sim > 0.3) are included. Questions are always included —
they're likely being answered. Reply chains bypass the check entirely.
Falls back to unfiltered context if the similarity check fails.

**After deploy:** run `!debug reembed` then `!summary create` to rebuild
clusters with the corrected embeddings.

**Modified files:**
- `utils/embedding_context.py` v1.3.0

---

### Version 5.7.1 — !explain detail

`!explain detail` extends the context receipt with the actual messages that
were injected into the bot's context, fetched live from the database.

- Messages truncated to 150 characters
- Clusters with > 10 messages show first 5 + last 5 with a gap line
- Supports `!explain detail <id>` for a specific response

**Modified files:**
- `commands/explain_commands.py` v1.1.0

---

### Version 5.7.0 — Explainability & Context Receipts

Every bot response now records a context receipt — a permanent log of exactly
what context was assembled: which clusters were retrieved and their scores,
whether fallback was used, always-on token counts, budget consumption, and
the query embedding path taken.

**`!explain`** — show the context receipt for the most recent bot response:
```
ℹ️ Context Receipt (response to: "how strong are squirrels?")
Query Embedding: raw
Always-On Context (278 tokens): Overview ✓, 8 key facts, 5 decisions, 3 action items
Retrieved Clusters (3,563 tokens):
  1. Squirrel Strength Discussion — score 0.846, 12 msgs (557 tok)
  2. Animal Strength Comparison — score 0.742, 25 msgs (3,006 tok)
Below Threshold: Bot Availability Check — score 0.21
Recent Messages: 5
Budget: 4,168 / 12,000 tokens (34.7%)
Provider: deepseek / deepseek-reasoner
```

**`!explain <message_id>`** — receipt for a specific response by Discord message ID.

Receipt storage never blocks or prevents bot responses — stored after send,
fails silently if the table write fails.

**New files:**
- `utils/receipt_store.py` v1.0.0 — save/get receipts in `response_context_receipts` table
- `commands/explain_commands.py` v1.0.0 — `!explain` command + `format_receipt()`

**Modified files:**
- `utils/embedding_context.py` v1.2.0 — `embed_query_with_smart_context()` returns
  `(vec, path_name)` tuple so callers can record which embedding path was taken
- `utils/context_retrieval.py` v1.2.0 — `_retrieve_cluster_context()` returns
  `(text, tokens, cluster_receipt)` 3-tuple; `_fallback_msg_search()` returns
  `(text, tokens, count)` 3-tuple
- `utils/context_manager.py` v2.4.0 — assembles full receipt dict, returns
  `(messages, receipt_data)` tuple from `build_context_for_provider()`
- `utils/response_handler.py` v1.2.0 — stores receipt after send via `save_receipt()`
- `bot.py` v3.1.0 — destructures `(messages, receipt_data)` at both call sites
- `commands/__init__.py` v2.6.0 — registers `explain_commands`

---

### Version 5.6.1 — Smart Query Embedding

Fixes topic bleed-through when the user switches topics mid-conversation.
Previously, a 3-message context window was always prepended to the query
embedding, causing "what database are we using?" to embed with gorilla context
and retrieve gorilla clusters.

**Two-path query embedding (`embed_query_with_smart_context()`):**

- **Path 1 — previous message was a question:** current message is likely a
  response (e.g., "yes" after "Should we use PostgreSQL?"). Include the question
  as context. 1 API call.
- **Path 2 — otherwise:** embed raw, then cosine-compare to the previous
  message's stored embedding. If `sim > RETRIEVAL_MIN_SCORE` (same topic),
  re-embed with context. If below (topic shift), use the raw embedding already
  computed. 1–2 API calls.

Question detection is a pure heuristic (`is_question()`) — no LLM call.
`build_contextual_text()` for stored embeddings is unchanged.

**Modified files:**
- `utils/embedding_context.py` v1.1.0 — `is_question()`, `embed_query_with_smart_context()`
- `utils/embedding_store.py` v1.9.0 — `get_stored_embedding(message_id)`
- `utils/context_retrieval.py` v1.1.0 — query path uses smart context

---

### Config tuning — RETRIEVAL_MIN_SCORE raised to 0.45

Set in `.env` (overrides config.py default of 0.25). With contextual embeddings
producing higher-signal vectors, the old 0.25 threshold was too permissive.
0.45 requires clusters to be meaningfully similar to the query before injection.

---

### Version 5.6.0 — Context-Prepended Embeddings + 250-Line Refactors

Two improvements in one release: (1) all embeddings now include conversational
context, and (2) all files brought under the 250-line limit.

**Context-prepended embeddings:**
Instead of embedding raw message content, the bot now prepends the 3 prior
messages (or the replied-to message chain) before embedding. This places short
replies ("yes", "agreed") in their conversational context rather than generic
affirmation space, and ensures bot responses cluster by topic rather than by
shared language patterns.

- `utils/embedding_context.py` v1.0.0 — `build_contextual_text()`,
  `get_previous_messages()`, `get_reply_context()`
- `utils/raw_events.py` v1.6.0 — embed path uses `build_contextual_text()`
- `utils/context_retrieval.py` v1.0.0 — query embedding uses last 3 in-memory
  conversation messages as context (same vector space as stored embeddings)
- `commands/cluster_commands.py` v1.0.0 — `!debug backfill` uses contextual text;
  new `!debug reembed` deletes all embeddings and re-embeds with context
- `utils/embedding_store.py` v1.8.0 — `get_messages_without_embeddings()` returns
  `(id, content, author, reply_to_id)` ordered chronologically; adds
  `delete_channel_embeddings()`

**250-line refactors (7 files fixed, 5 new modules extracted):**

| Extracted to | From | Lines moved |
|---|---|---|
| `utils/topic_store.py` | `embedding_store.py` | topic functions (~150 lines) |
| `utils/context_retrieval.py` | `context_manager.py` | retrieval functions (~110 lines) |
| `utils/summary_prompts_structurer.py` | `summary_prompts_authoring.py` | Structurer prompt (~90 lines) |
| `commands/cluster_commands.py` | `debug_commands.py` | cluster commands (~185 lines) |

Inline trims: `summary_display.py`, `message_store.py`, `cleanup_coordinator.py`.

**Post-deploy steps required:**
1. `!debug reembed` — delete + re-embed all messages with contextual text
2. `!summary create` — rebuild clusters from contextual embeddings

**Modified files:** embedding_context.py (new), topic_store.py (new),
context_retrieval.py (new), summary_prompts_structurer.py (new),
cluster_commands.py (new), embedding_store.py, context_manager.py,
summary_prompts_authoring.py, debug_commands.py, raw_events.py,
summary_display.py, message_store.py, cleanup_coordinator.py,
summarizer_authoring.py, commands/__init__.py

---

### Version 5.5.1 — ℹ️ Prefix Fix + Bot Diagnostic Embedding Guard

Two bugs fixed, one sklearn warning silenced.

**Bug 1 (root cause): `!debug clusters` pagination missing ℹ️ prefix**
`debug_clusters` had a manual chunk loop calling `ctx.send(page)` without
the prefix. Pages 2+ entered Discord as bare text, were embedded by
`raw_events.py`, assigned to clusters, and retrieved as conversation context
(confirmed: cluster report text was retrieved when a user asked about squirrels).
Fix: both `debug_clusters` and `debug_summarize_clusters` now route through
`send_paginated()` — all chunks guaranteed to carry ℹ️.

**Bug 2 (belt-and-suspenders): no guard against prefix loss in general**
Added `_looks_like_diagnostic()` to `raw_events.py`. Bot-authored messages
whose content starts with `Cluster `, `Parameters:`, `Processed:`,
`**Cluster Analysis`, `**Cluster Summariz`, or `**Overview**` are skipped
at the embedding gate even if prefix loss recurs.

**Data cleanup:** 2 contaminated embeddings/cluster memberships deleted from
production DB; 60 clusters marked `needs_resummarize=1` and re-summarized
via `!summary update`.

**sklearn FutureWarning:** Added `copy=False` to `HDBSCAN()` call in
`cluster_engine.py` to silence "default value of copy will change in 1.10".

**Modified files:**
- `commands/debug_commands.py` v1.6.0 — `send_paginated()` for all pagination
- `utils/raw_events.py` v1.5.0 — `_looks_like_diagnostic()` guard
- `utils/cluster_engine.py` v1.0.1 — `copy=False` on HDBSCAN

---

### Version 5.5.0 — Cluster-Based Retrieval Integration

Replaces topic-based semantic retrieval with cluster-based retrieval in the
bot's response path. When a user message arrives, the bot scores it against
cluster centroids (instead of topic embeddings) and injects the matching
cluster's direct member messages into the context. The full v5 architecture
is now live end-to-end.

**What changed:**
- `context_manager.py` `_retrieve_cluster_context()` replaces `_retrieve_topic_context()`
- Imports `find_relevant_clusters` + `get_cluster_messages` from new `cluster_retrieval.py`
- All unchanged: `[Topic: {label}]` section framing, fallback path, token budget,
  timestamp prefixing, today's date injection, `_fallback_msg_search()`

**Quality improvement:**
- Topics (v4.x): LLM-generated labels, messages linked by cosine similarity approximation
- Clusters (v5.x): messages grouped directly by HDBSCAN with exact membership;
  centroid is the actual mean vector — no linking approximation

**New files:**
- `utils/cluster_retrieval.py` v1.0.0 — `find_relevant_clusters()`, `get_cluster_messages()`

**Modified files:**
- `utils/context_manager.py` v2.2.0 — cluster retrieval replaces topic retrieval

**Retained (rollback):** topic functions in `embedding_store.py` unchanged

---

### Version 5.4.0 — Incremental Cluster Assignment + Selective Re-Summarization

On-arrival cluster assignment routes each new embedded message to its nearest
cluster centroid without running a full re-cluster. `!summary update` re-summarizes
only the clusters that received new messages since the last run.

**Three-tier architecture:**
1. **Tier 1 (on arrival)**: `raw_events.py` calls `assign_to_nearest_cluster()` after
   embedding — cosine similarity vs cluster centroids, updates centroid via running
   average + renormalize, marks cluster `needs_resummarize=1`
2. **Tier 2 (`!summary update`)**: `quick_update_channel()` re-summarizes only dirty
   clusters (Gemini per-cluster), then re-runs classify → overview → dedup → answered-Q → save
3. **Tier 3 (`!summary create`)**: full re-cluster (unchanged)

**Key design choices:**
- Centroid update via running average: `(old * n + new) / (n+1)`, then normalize
- `assign_to_nearest_cluster` fails silently — no clusters is not an error
- `cluster_count` and `noise_message_count` preserved from existing summary (no re-cluster)
- Unassigned count reported in `!summary update` output as prompt to run `!summary create`

**New files:**
- `schema/006.sql` — `ALTER TABLE clusters ADD COLUMN needs_resummarize INTEGER DEFAULT 0`
- `utils/cluster_assign.py` v1.0.0 — `assign_to_nearest_cluster()`, cosine similarity,
  centroid running average update, `_update_and_assign()`
- `utils/cluster_update.py` v1.0.0 — `run_quick_update()`, re-summarizes dirty clusters,
  re-runs full post-processing pipeline, preserves cluster_count + noise_count

**Modified files:**
- `utils/cluster_store.py` v2.0.0 — added `get_dirty_clusters()`, `mark_clusters_clean()`,
  `get_unassigned_message_count()`
- `utils/raw_events.py` v1.4.0 — calls `assign_to_nearest_cluster` after embedding
- `utils/summarizer.py` v3.1.0 — added `quick_update_channel()`
- `commands/summary_commands.py` v2.4.0 — added `!summary update` subcommand

---

### Version 5.3.0 — Cluster Pipeline (validated + committed)

`!summary create` now runs the full cluster-v5 pipeline. Validated on #openclaw:
741 messages, 56 clusters, 0 failures, ~$0.01 total cost.

**Pipeline order:**
1. UMAP + HDBSCAN clustering (`cluster_engine.py`)
2. Per-cluster Gemini summarization — one call per cluster (`cluster_summarizer.py`)
3. Aggregate structured items (decisions, key_facts, action_items, open_questions) across all clusters
4. GPT-4o-mini classifier — whitelist filter, default-to-DROP on missing verdict (`cluster_classifier.py`)
5. Overview Gemini call — labels + summary texts only → overview + participants (`cluster_overview.py`)
6. Merge overview + participants + filtered items
7. `translate_to_channel_summary()` — maps `text` → `fact`/`task`/`question`/`decision`
8. Embedding dedup — cosine similarity 0.85 threshold, all four arrays (`cluster_qa.py`)
9. Answered-question check — GPT-4o-mini YES/NO per question vs decisions + facts (`cluster_qa.py`)
10. `save_channel_summary()`

**Key design choices:**
- Classifier runs BEFORE overview LLM — prevents 16K+ token JSON blowup from 56 clusters
- Overview receives labels + summary text only (not structured fields) — tiny response
- Embedding dedup handles "Use PostgreSQL" × 3 etc. without LLM reluctance
- Answered-question check is a targeted binary classification — works well with GPT-4o-mini
- Default-to-DROP on missing classifier verdicts — truncation produces less noise, not more
- v4.x three-pass pipeline retained in `summarizer_authoring.py` — rollback safety only

**New files (v5.3.0 final):**
- `utils/cluster_overview.py` v2.2.0 — `generate_overview()`, `_collect_structured_items()`,
  `translate_to_channel_summary()`, `run_cluster_pipeline()` orchestrator
- `utils/cluster_classifier.py` v1.6.0 — GPT-4o-mini whitelist filter; `classify_overview_items()`,
  `_build_prompt()`, `_apply_verdicts()` (default-to-DROP); `CLASSIFIER_SYSTEM_PROMPT` with
  6-category KEEP whitelist
- `utils/cluster_qa.py` v1.0.0 — post-classifier QA; `deduplicate_summary()` (embedding cosine
  dedup, 0.85 threshold), `remove_answered_questions()` (GPT-4o-mini YES/NO)

**Modified files:**
- `utils/summarizer.py` v3.0.0 — `summarize_channel()` routes to `run_cluster_pipeline()`
- `utils/summary_commands.py` v2.3.0 — `!summary create` displays cluster-v5 stats;
  `!summary clear` also calls `clear_channel_clusters()`
- `utils/summary_display.py` v1.3.2 — footer detects cluster-v5 schema, shows
  `N clusters (M noise) | cluster-v5` instead of `0 messages | 0 tokens`

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
│   ├── 005.sql                    # v5.1.0 clusters, cluster_messages
│   └── 006.sql                    # v5.4.0 needs_resummarize column
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
│   ├── summary_commands.py        # v2.4.0
│   └── debug_commands.py          # v1.6.0
│   └── debug_commands.py          # v1.5.0
├── utils/
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
│   ├── models.py                  # v1.2.0
│   ├── message_store.py           # v1.2.0
│   ├── raw_events.py              # v1.5.0
│   ├── db_migration.py            # v1.0.0
│   ├── embedding_store.py         # v1.5.0
│   ├── context_manager.py         # v2.2.0
│   ├── response_handler.py        # v1.1.4
│   ├── summarizer.py              # v3.1.0
│   ├── summarizer_authoring.py    # v1.10.2
│   ├── summary_schema.py          # v1.4.0
│   ├── summary_delta_schema.py    # v1.0.0
│   ├── summary_classifier.py      # v1.3.0
│   ├── summary_store.py           # v1.1.0
│   ├── summary_prompts.py         # v1.6.0
│   ├── summary_prompts_authoring.py  # v1.6.0
│   ├── summary_display.py         # v1.3.2
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
