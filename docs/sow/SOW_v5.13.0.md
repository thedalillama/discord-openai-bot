# SOW v5.13.0 — Embedding Noise Filter Tightening
# Status: PROPOSED — awaiting approval
# Branch: claude-code
# Prerequisite: v5.12.0

---

## Problem Statement

Cluster diagnostic on 182 clusters / 2,573 messages shows 8 WEAK clusters
(4.4%) containing 184 messages (7.2%) that add no semantic value. Zero
NOISE clusters, 77% STRONG. The pipeline is healthy overall, but the
weak clusters waste embedding budget, dilute cluster quality, and
pollute retrieval.

The 8 weak clusters break down into three categories:

1. **Bot-forwarded deleted content** (112 msgs, 2 clusters):
   "[Original Message Deleted]" from Midjourney announcements. Not
   caught by the ℹ️/⚙️ prefix filter because these are cross-bot
   forwards, not our bot's output.

2. **Repeated identical commands** (14+ msgs, 1-2 clusters):
   "continue" repeated 14 times. Each gets its own embedding and
   clusters with the other copies.

3. **Ultra-thin messages** (scattered across clusters):
   Bare "?", "thanks", single-word acknowledgments. Context
   prepending helps but can't make these semantically meaningful.

All three categories pass the current noise guard because they don't
start with `!`, `ℹ️`, `⚙️`, or match `_DIAGNOSTIC_PREFIXES`.

## Objective

Add a `_should_skip_embedding()` function to `raw_events.py` that
catches these three categories at embed time. Messages are still
stored in SQLite (persistence is unchanged) — they just don't get
embedded or cluster-assigned.

No behavioral change to the response pipeline, retrieval, or
summarization. Existing weak-cluster messages remain until the next
`!debug reembed` + `!summary create`.

## Design

### New function: `_should_skip_embedding(content, is_bot_author)`

Replaces the inline noise checks and `_looks_like_diagnostic()` with
a single, comprehensive guard. Returns `True` if the message should
not be embedded.

```python
# Minimum word count for a message to be worth embedding.
# Messages with fewer words are too thin to carry semantic meaning
# even with context prepending. Questions (ending with ?) are exempt
# — even short questions like "why?" have retrieval value.
MIN_EMBED_WORDS = 4

# Content patterns that indicate non-conversational messages
_SKIP_CONTENT = {
    "[original message deleted]",
}

# Diagnostic output prefixes (existing, moved from module level)
_DIAGNOSTIC_PREFIXES = (
    'Cluster ', 'Parameters:', 'Processed:',
    '**Cluster Analysis', '**Cluster Summariz', '**Overview**',
)
_DIAGNOSTIC_SUBSTRINGS = (
    'Type !help command for more info',
)


def _should_skip_embedding(content, is_bot_author):
    """Determine if a message should be skipped for embedding.

    Messages are still stored in SQLite — this only controls whether
    they enter the embedding/clustering pipeline.

    Skip criteria:
    1. Empty or whitespace-only
    2. Commands (! prefix) or bot output (ℹ️/⚙️ prefix)
    3. Bot diagnostic output (existing _looks_like_diagnostic)
    4. Known non-conversational content (deleted message placeholders)
    5. Too short to carry semantic meaning (< MIN_EMBED_WORDS),
       unless it's a question
    """
    if not content or not content.strip():
        return True

    # Existing prefix filters
    if content.startswith(('!', 'ℹ️', '⚙️')):
        return True

    # Existing diagnostic guard (bot-authored only)
    if is_bot_author:
        if (any(content.startswith(p) for p in _DIAGNOSTIC_PREFIXES) or
                any(s in content for s in _DIAGNOSTIC_SUBSTRINGS)):
            return True

    # Known non-conversational content
    if content.strip().lower() in _SKIP_CONTENT:
        return True

    # Too short to embed — unless it's a question
    words = content.split()
    if len(words) < MIN_EMBED_WORDS and not content.rstrip().endswith('?'):
        return True

    return False
```

### Why exempt questions

Short questions like "why?", "how?", "PostgreSQL?" have high retrieval
value — a user asking "what database?" should match a prior "PostgreSQL?"
exchange. Questions are also naturally handled by the smart query
embedding path. Filtering them would create blind spots.

### Why MIN_EMBED_WORDS = 4

Messages of 1–3 words ("yes", "ok sure", "sounds good") are
acknowledgments whose meaning is entirely dependent on context. Context
prepending helps the embedding model, but the resulting embedding is
still dominated by the thin content. At 4+ words, messages typically
carry enough standalone semantic signal ("let's use PostgreSQL instead",
"I agree with that approach") to produce a useful embedding.

This threshold is configurable — if it's too aggressive, raise it to 3
or lower to 5 after observing results.

### Integration in raw_events.py

Replace the current inline check:

```python
# BEFORE (current):
if content and not content.startswith(('!', 'ℹ️', '⚙️')):
    if msg.is_bot_author and _looks_like_diagnostic(content):
        logger.debug(f"Skipping unprefixed bot diagnostic msg {msg.id}")
        return
    # ... embed and assign ...

# AFTER:
if content and not _should_skip_embedding(content, msg.is_bot_author):
    # ... embed and assign ...
```

The same function should also be applied in `get_messages_without_embeddings()`
in `embedding_store.py` so that `!debug backfill` and `!debug reembed` skip
the same messages. Currently that function filters with SQL:

```sql
AND m.content NOT LIKE '!%'
AND m.content NOT LIKE 'ℹ️%'
AND m.content NOT LIKE '⚙️%'
```

Add equivalent SQL filters for the new criteria:

```sql
AND m.content NOT LIKE '[Original Message Deleted]'
AND LENGTH(m.content) - LENGTH(REPLACE(m.content, ' ', '')) + 1 >= 4
    OR m.content LIKE '%?'
```

Note: The word-count SQL is approximate (splits on spaces). For exact
parity with Python, an alternative is to apply `_should_skip_embedding()`
in Python after the SQL query returns. Given the small scale (<2K msgs),
the Python filter is cleaner and avoids fragile SQL string math.

### Alternative: Python-side filter in backfill

Instead of complex SQL, keep the existing SQL filters and add a Python
filter after fetch:

```python
def get_messages_without_embeddings(channel_id, limit=500):
    # ... existing SQL query ...
    rows = conn.execute(...).fetchall()
    return [(r[0], r[1], r[2], r[3]) for r in rows
            if not _should_skip_embedding(r[1], False)]
```

This requires importing `_should_skip_embedding` from `raw_events` or
extracting it to a shared location. Given the 250-line limit, extracting
to a small utility makes sense if `raw_events.py` is close to the limit.

---

## Files Changed

| File | Version | Change |
|------|---------|--------|
| `utils/raw_events.py` | v1.8.0 | Add `_should_skip_embedding()`; replace inline checks; remove `_looks_like_diagnostic()` (subsumed) |
| `utils/embedding_store.py` | v1.10.0 | Apply thin-message filter to `get_messages_without_embeddings()` |
| `STATUS.md` | v5.13.0 | Add version entry |
| `HANDOFF.md` | — | Update noise guard docs; remove Known Limitation #3 (legacy cluster noise — resolved by reembed after this change) |
| `CLAUDE.md` | — | Update noise guard reference |
| `README.md` | — | No change needed |

---

## Post-Deploy Steps

After deploying v5.13.0, run in each active channel:

```
!debug reembed
!summary create
```

This re-embeds all messages through the new filter (thin messages
skipped), then rebuilds clusters from the cleaned embeddings. The 8
weak clusters should disappear or merge into stronger clusters.

---

## Testing

1. `python -c "import bot"` — import chain valid.
2. Restart bot. Send a thin message ("ok"). Check logs for skip.
3. Send a short question ("why?"). Verify it IS embedded.
4. Send a 4+ word message. Verify it IS embedded.
5. Run `!debug reembed` + `!summary create` on a test channel.
6. Run `cluster_diagnostic.py` — WEAK clusters should drop to 0–2.
7. `!explain` after a response — verify retrieval still works.

---

## Constraints

1. Full files only — no partial patches
2. Increment version numbers
3. 250-line file limit
4. Messages always stored in SQLite — filter only affects embedding
5. Questions exempt from word-count filter
6. All development on `claude-code` branch
7. Update documentation alongside code changes
