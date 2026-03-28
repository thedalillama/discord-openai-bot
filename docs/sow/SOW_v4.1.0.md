# SOW v4.1.0 — Direct Message Embedding Fallback
# Status: APPROVED

## Problem

v4.0.0 topic retrieval works when a query matches an existing topic. When it
doesn't — because the exchange was too short for the Structurer to create a
topic, or the query is too tangential — retrieval returns empty and falls back
to full summary injection. The specific messages are embedded and sitting in
`message_embeddings`, but there is no path to surface them.

## Solution

Add `_fallback_msg_search()` as a second retrieval path in
`_retrieve_topic_context()`. When topic retrieval returns empty, search
`message_embeddings` directly using cosine similarity against the already-
computed query embedding.

The query vector is already computed at the failure points. The message
embeddings are already stored (~570 messages). This is a small addition,
not a new system.

## Flow After Change

```
User sends a message
  → Embed message (already happening)
  → Find topics above RETRIEVAL_MIN_SCORE
      → Topics found:
          → Pull topic-linked messages (unchanged)
      → No topics found:
          → Search message_embeddings directly via cosine similarity
          → Return top-N most similar messages (up to RETRIEVAL_MSG_FALLBACK)
  → Inject into context (same budget logic, same system prompt framing)
  → If both empty: fall back to full summary injection (unchanged)
```

## Files Changed

| File | From | To | Change |
|------|------|----|--------|
| `utils/embedding_store.py` | v1.2.0 | v1.3.0 | Add `find_similar_messages()` |
| `utils/context_manager.py` | v2.0.4 | v2.1.0 | Add `_fallback_msg_search()`, call from both failure points |
| `config.py` | v1.12.5 | v1.12.6 | Add `RETRIEVAL_MSG_FALLBACK` (default 15) |
| `STATUS.md` | v4.0.0 | v4.1.0 | Update |
| `HANDOFF.md` | v4.0.0 | v4.1.0 | Update |
| `README.md` | v4.0.0 | v4.1.0 | Update |
| `README_ENV.md` | v4.0.0 | v4.1.0 | Add RETRIEVAL_MSG_FALLBACK |

No changes to: summarizer pipeline, topic storage, always-on context,
debug commands, any provider, any schema.

## Implementation Details

### `utils/embedding_store.py` — `find_similar_messages()`

```python
def find_similar_messages(query_vec, channel_id, top_n=15,
                           min_score=0.0, exclude_ids=None):
    """Search message_embeddings directly for messages similar to query.
    Used as fallback when topic-based retrieval returns empty.
    Returns list of (message_id, author_name, content, score), score descending.
    """
    exclude_ids = set(exclude_ids or [])
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT me.message_id, m.author_name, m.content, me.embedding "
            "FROM message_embeddings me JOIN messages m ON m.id=me.message_id "
            "WHERE m.channel_id=? AND m.is_deleted=0 AND m.content!='' "
            "  AND m.content NOT LIKE '!%' "
            "  AND m.content NOT LIKE '\u2139\ufe0f%' "
            "  AND m.content NOT LIKE '\u2699\ufe0f%'",
            (channel_id,)).fetchall()
    finally:
        conn.close()

    scored = []
    for mid, author, content, blob in rows:
        if mid in exclude_ids:
            continue
        score = cosine_similarity(query_vec, unpack_embedding(blob))
        if score >= min_score:
            scored.append((mid, author, content, score))
    scored.sort(key=lambda x: x[3], reverse=True)
    return scored[:top_n]
```

### `utils/context_manager.py` — `_fallback_msg_search()`

New module-level helper. Calls `find_similar_messages()`, trims to fit
token budget, returns formatted section string.

```python
def _fallback_msg_search(query_vec, channel_id, token_budget, recent_ids):
    """Direct message embedding search when topic retrieval returns empty."""
    try:
        from utils.embedding_store import find_similar_messages
        msgs = find_similar_messages(
            query_vec, channel_id,
            top_n=RETRIEVAL_MSG_FALLBACK,
            exclude_ids=recent_ids)
        if not msgs:
            return "", 0
        parts, used = [], 0
        for _, author, content, _ in msgs:
            line = f"{author}: {content}"
            lt = estimate_tokens(line) + 1
            if used + lt > token_budget:
                break
            parts.append(line)
            used += lt
        if not parts:
            return "", 0
        section = "[Retrieved by message similarity]\n" + "\n".join(parts)
        logger.debug(
            f"Fallback: {len(parts)} msgs ({used} tokens) ch:{channel_id}")
        return section, used
    except Exception as e:
        logger.warning(f"Fallback search failed ch:{channel_id}: {e}")
        return "", 0
```

### `_retrieve_topic_context()` — Two call sites

`recent_ids` moved before the topic filter (currently after) so it is
available at both failure points.

**Failure point 1** — no topics above threshold:
```python
if not topics:
    return _fallback_msg_search(query_vec, channel_id, token_budget, recent_ids)
```

**Failure point 2** — topics found but all returned 0 messages:
```python
if not lines:
    return _fallback_msg_search(query_vec, channel_id, token_budget, recent_ids)
```

### Line Count Management

context_manager.py is at 249 lines. To stay under 250:
- Remove verbose per-topic debug logs added during troubleshooting
  (the `topic {id}: 0 messages` and `budget exceeded` per-iteration logs)
- Use set comprehension for `recent_ids`
- These were diagnostic aids; the system is stable and they are no longer needed

### `config.py` — New Variable

```python
# RETRIEVAL_MSG_FALLBACK: max messages returned by direct embedding fallback.
RETRIEVAL_MSG_FALLBACK = int(os.environ.get('RETRIEVAL_MSG_FALLBACK', 15))
```

## Test Plan

| Test | Query | Expected |
|------|-------|----------|
| Regression | "did we discuss gorillas?" | Topic retrieval fires, topic-linked messages returned. Logs: `Topics above threshold` |
| Fallback — non-topic content | Topic about Dario Amodei not in topics table | Fallback fires, Dario messages returned by embedding similarity. Logs: `Fallback: N msgs` |
| Fallback — orphaned exchange | Brief exchange Structurer didn't capture as topic | Fallback surfaces those messages |
| True negative | "what did we discuss about quantum physics?" | Both topic and fallback return empty. Bot correctly reports no prior discussion |
| Budget respected | Any fallback query | Logs show token count within budget |

## Constraints

- Full files only — no partial diffs
- Increment version numbers in file heading comments
- Keep files under 250 lines
- Update STATUS.md, HANDOFF.md, README.md, README_ENV.md
- No changes to summarizer pipeline, topic storage, or commands
