# HANDOFF.md
# Version 4.1.3
# Agent Development Handoff Document

## Current Status

**Branch**: claude-code
**Bot version**: v4.1.3 (pending deploy)
**Bot**: Running on GCP VM as systemd service (`discord-bot`)
**Main branch**: tagged v4.0.0

---

## What Just Happened

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

### Three-Pass Summarization Pipeline (both cold start + incremental)
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

### 1. Deploy and test v4.1.1
```
1. sudo systemctl restart discord-bot
2. Ask "what have we said about bonobos?" — key facts framing fix
   → Expect: model answers from key facts ("common ancestor ~6-8 million years ago")
3. Ask about gorillas (topic exists)
   → Expect: topic retrieval fires as before (regression check)
4. Ask about quantum physics (not discussed)
   → Expect: both paths empty, full summary fallback
```

### 2. Merge claude-code → development → main as v4.1.1

---

## File Versions

### Semantic Retrieval Files (v4.1.0)
| File | Version | Key Role |
|------|---------|----------|
| `utils/embedding_store.py` | v1.3.0 | OpenAI embeddings, topic linking, direct fallback search |
| `utils/context_manager.py` | v2.1.0 | Always-on + retrieval + fallback, budget, 5-msg cap |
| `utils/summary_display.py` | v1.3.1 | format_always_on_context() — key facts framing fix |
| `utils/embedding_store.py` | v1.5.0 | clear_channel_topics() + _is_noise_topic() filter |
| `utils/summarizer_authoring.py` | v1.10.2 | calls clear_channel_topics() before topic loop |
| `utils/raw_events.py` | v1.3.0 | Embed on arrival |
| `utils/summarizer_authoring.py` | v1.10.1 | Store active + archived topics |
| `commands/debug_commands.py` | v1.2.0 | !debug backfill |
| `config.py` | v1.12.6 | All retrieval config vars incl. RETRIEVAL_MSG_FALLBACK |
| `schema/004.sql` | — | topics, topic_messages, message_embeddings |

### Summarization Pipeline Files
| File | Version | Key Role |
|------|---------|----------|
| `utils/summarizer.py` | v2.1.0 | Orchestrator, delegates to pipeline |
| `utils/summarizer_authoring.py` | v1.10.1 | Three-pass pipeline (shared) |
| `utils/summary_delta_schema.py` | v1.0.0 | anyOf schema + translate_ops() |
| `utils/summary_classifier.py` | v1.3.0 | GPT-4o-mini + existing dedup |
| `utils/summary_prompts.py` | v1.6.0 | Incremental prompt (camelCase) |
| `utils/summary_prompts_authoring.py` | v1.5.0 | Secretary/Structurer prompts |
| `utils/summary_schema.py` | v1.4.0 | apply_ops(), verify, DELTA_SCHEMA |
| `utils/summary_store.py` | v1.1.0 | SQLite read/write |
| `ai_providers/gemini_provider.py` | v1.2.1 | use_json_schema for anyOf |

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
