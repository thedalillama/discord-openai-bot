# SOW v5.12.0 — Similarity Threshold Rename & Separation
# Status: PROPOSED — awaiting approval
# Branch: claude-code
# Prerequisite: v5.11.0 merged to all branches

---

## Problem Statement

Three cosine similarity thresholds control different pipeline stages,
but their names don't communicate what they do:

1. **`CONTEXT_SIMILARITY_THRESHOLD = 0.3`** (hardcoded in
   `embedding_context.py`) — at embed time, filters which previous
   messages are included as context in the `[Context: ...]` prefix
   before a message is embedded and stored.

2. **`RETRIEVAL_MIN_SCORE`** (config.py, default 0.25, production
   0.5) — at query time, reused in `embed_query_with_smart_context()`
   as the topic-shift detection threshold. This is a different concern
   from cluster retrieval but shares the same variable.

3. **`RETRIEVAL_MIN_SCORE`** (same variable) — at retrieval time,
   filters which clusters are relevant enough to inject into context.

Problems:
- `CONTEXT_SIMILARITY_THRESHOLD` is vague — "context" of what?
- `RETRIEVAL_MIN_SCORE` does double duty for two unrelated decisions
  (topic-shift detection vs cluster relevance filtering). They cannot
  be tuned independently.
- Documentation is inconsistent: README.md says production is `0.45`,
  README_ENV.md says `0.5`, HANDOFF.md header says `0.45`.

## Objective

1. Rename thresholds to descriptive names.
2. Split `RETRIEVAL_MIN_SCORE` into two independent variables.
3. Make the embed-time threshold configurable via `.env`.
4. Fix documentation inconsistencies on production values.
5. No behavioral change — all thresholds keep their current values.

## Design

### New Names

| Current | New | Where Used | Default |
|---------|-----|------------|---------|
| `CONTEXT_SIMILARITY_THRESHOLD` (hardcoded 0.3) | `EMBEDDING_CONTEXT_MIN_SCORE` | `embedding_context.py` `build_contextual_text()` — filters previous messages included as embedding context | `0.3` |
| `RETRIEVAL_MIN_SCORE` (used in `embed_query_with_smart_context`) | `QUERY_TOPIC_SHIFT_THRESHOLD` | `embedding_context.py` `embed_query_with_smart_context()` — detects whether user changed topics | `0.5` |
| `RETRIEVAL_MIN_SCORE` (used in `context_retrieval.py`) | `RETRIEVAL_MIN_SCORE` (unchanged) | `context_retrieval.py` — filters clusters for injection | `0.25` |

### Why separate QUERY_TOPIC_SHIFT_THRESHOLD from RETRIEVAL_MIN_SCORE

These answer different questions:
- **Topic shift** (query time): "Is the user still talking about the
  same thing as their last message?" Controls whether the query gets
  re-embedded with conversational context or stays raw.
- **Cluster relevance** (retrieval time): "Is this cluster similar
  enough to the query to inject into the response?" Controls what
  context the LLM sees.

A user might shift topics (low similarity to previous message) but
still have highly relevant clusters for the new topic. Or they might
stay on-topic (high similarity to previous message) but the best
cluster is borderline. These are independent decisions.

### config.py Changes

```python
# Embedding context threshold (SOW v5.12.0)
# Minimum cosine similarity for a previous message to be included as
# context when building the [Context: ...] prefix for stored embeddings.
# Lower = more inclusive (more context prepended). Questions always pass.
EMBEDDING_CONTEXT_MIN_SCORE = float(
    os.environ.get('EMBEDDING_CONTEXT_MIN_SCORE', 0.3))

# Query topic-shift threshold (SOW v5.12.0)
# When embedding a user query at response time, cosine similarity to
# the previous message below this threshold = topic shift → use raw
# embedding. Above = same topic → re-embed with conversational context.
QUERY_TOPIC_SHIFT_THRESHOLD = float(
    os.environ.get('QUERY_TOPIC_SHIFT_THRESHOLD', 0.5))

# RETRIEVAL_MIN_SCORE: unchanged — cluster relevance threshold.
```

Remove `TOPIC_LINK_MIN_SCORE` comment reference to v4.x rollback
(topics table dropped in schema/007.sql). Keep the variable itself
since it's still in config.py — mark the comment as legacy/unused.

### embedding_context.py Changes

Replace hardcoded `CONTEXT_SIMILARITY_THRESHOLD = 0.3` with import:
```python
from config import EMBEDDING_CONTEXT_MIN_SCORE, QUERY_TOPIC_SHIFT_THRESHOLD
```

In `build_contextual_text()`:
```python
# Before:
if cosine_similarity(cur_vec, prev_vec) > CONTEXT_SIMILARITY_THRESHOLD:
# After:
if cosine_similarity(cur_vec, prev_vec) > EMBEDDING_CONTEXT_MIN_SCORE:
```

In `embed_query_with_smart_context()`:
```python
# Before:
from config import RETRIEVAL_MIN_SCORE
...
if sim > RETRIEVAL_MIN_SCORE:
# After (QUERY_TOPIC_SHIFT_THRESHOLD already imported at top):
if sim > QUERY_TOPIC_SHIFT_THRESHOLD:
```

Also update the debug log line that references `RETRIEVAL_MIN_SCORE`:
```python
# Before:
f"Query Path 2: sim={sim:.3f} vs threshold={RETRIEVAL_MIN_SCORE} "
# After:
f"Query Path 2: sim={sim:.3f} vs threshold={QUERY_TOPIC_SHIFT_THRESHOLD} "
```

### Documentation Consistency Fix

Confirm actual production `.env` value for `RETRIEVAL_MIN_SCORE` and
update all docs to match. Current inconsistency:
- README.md says `0.45`
- README_ENV.md says `0.5`
- HANDOFF.md header says `0.45`

---

## Files Changed

| File | Version | Change |
|------|---------|--------|
| `config.py` | v1.15.0 | Add `EMBEDDING_CONTEXT_MIN_SCORE`, `QUERY_TOPIC_SHIFT_THRESHOLD`; update comments |
| `utils/embedding_context.py` | v1.5.0 | Import new config vars; replace `CONTEXT_SIMILARITY_THRESHOLD` and `RETRIEVAL_MIN_SCORE` usage |
| `README_ENV.md` | — | Add new variables to table; fix production value inconsistency |
| `README.md` | — | Update config table with new variable names; fix production value |
| `CLAUDE.md` | — | Update threshold references |
| `STATUS.md` | v5.12.0 | Add version entry |
| `HANDOFF.md` | — | Update threshold references; fix production value; remove Known Limitation #3 (addressed by making thresholds configurable and properly named) |
| `AGENT.md` | — | Update architecture context if threshold names appear |

No changes to: `context_retrieval.py` (still uses `RETRIEVAL_MIN_SCORE`
from config — unchanged), `cluster_retrieval.py`, `response_handler.py`,
`bot.py`, or any schema files.

---

## What This Does NOT Do

- No value changes — all thresholds keep their current numeric values.
- No reembed required — embedding logic is unchanged, just the
  variable names.
- No new features — pure rename and separation for clarity.

---

## Testing

1. `python -c "import bot"` — import chain validates.
2. Restart bot, send messages — verify embed-time logging shows
   `EMBEDDING_CONTEXT_MIN_SCORE` not `CONTEXT_SIMILARITY_THRESHOLD`.
3. Send a topic-shift message — verify query-time logging shows
   `QUERY_TOPIC_SHIFT_THRESHOLD` not `RETRIEVAL_MIN_SCORE`.
4. `!explain` after a response — verify receipt shows correct
   embedding path (raw vs similarity_context vs question_context).
5. Grep for old names — zero hits outside of git history and
   changelogs.

---

## Constraints

1. Full files only — no partial patches
2. Increment version numbers
3. 250-line file limit
4. No behavioral change — values stay the same
5. All development on `claude-code` branch
6. Update all documentation alongside code changes
