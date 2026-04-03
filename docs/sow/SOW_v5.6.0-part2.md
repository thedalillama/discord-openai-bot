# SOW v5.6.0 — Context-Prepended Embeddings
# Part 2 of 2: Re-embedding, Re-clustering, Testing
# Status: PROPOSED — awaiting approval
# Branch: claude-code

---

## Re-embedding Existing Messages

All existing embeddings were created without context. They are in
a different vector space than context-prepended embeddings and
cannot be mixed. All messages must be re-embedded.

### Process

1. Delete all rows from `message_embeddings`
2. Run `!debug backfill` which now uses `build_contextual_text()`
3. Messages are embedded in chronological order so context is
   available for each message
4. The first 3 messages in a channel have less context (0-2
   previous messages) — this is fine, they embed with whatever
   context is available

### Edge Case: First Messages in Channel

The first message has no context — embed it as-is (plain content).
The second message has 1 message of context. The third has 2. By
the fourth message onward, full context window (3) is available.
`build_contextual_text()` handles this gracefully — it returns
whatever context exists.

### Re-Embedding Command

Update `!debug backfill` to:
1. Accept an optional `--reembed` flag that deletes existing
   embeddings before re-embedding
2. Use `build_contextual_text()` instead of raw content
3. Process in chronological order (important for context)

```
!debug backfill --reembed
```

Without `--reembed`, it only embeds messages that don't have
embeddings yet (current behavior, but now with context).

---

## Re-clustering After Re-embedding

After re-embedding all messages, the existing clusters are invalid
(built from old embeddings). Run:

```
!summary create
```

This does a full re-cluster with the new embeddings and
re-summarizes everything. The clusters should be qualitatively
different — short replies will cluster with their conversations
instead of with other short replies.

---

## What Does NOT Change

- `embed_text()` in `embedding_store.py` — still calls OpenAI API
  with whatever text it receives
- `embed_and_store_message()` — still takes (message_id, text)
- `pack_embedding()` / `unpack_embedding()` — unchanged
- Cluster schema — unchanged
- Cluster retrieval in `context_manager.py` — unchanged except
  query embedding now uses context
- Per-cluster summarization — unchanged
- Classifier, dedup, QA — unchanged
- `find_similar_messages()` fallback — unchanged (searches
  message_embeddings which now contain contextual embeddings)
- Always-on context — unchanged
- Incremental assignment (`cluster_assign.py`) — unchanged (uses
  the embedding already stored, which is now contextual)

---

## Testing Plan

### Test 1: Context Construction
Verify `build_contextual_text()` output for various cases:
- Normal message with 3 previous messages
- Message with `reply_to_message_id` referencing a message 20
  messages back
- First message in channel (no context)
- Message after a long gap (context from hours/days ago — still
  valid, previous messages are previous messages)

Log the contextual text at DEBUG level during backfill so we can
inspect samples.

### Test 2: Re-embed and Re-cluster
Run `!debug backfill --reembed` then `!summary create`. Compare
cluster composition against v5.5.0 clusters:

**Expected improvements:**
- Short replies ("yes", "agreed", "good point") cluster with the
  conversations they belong to, not with other short replies
- Bot responses about different topics are in separate clusters
  (gorilla response with gorilla discussion, database response
  with database discussion)
- The "bonobos" repeated-word cluster should be smaller or merged
  into the animal discussion cluster (context differs per instance)

**Cluster count may change** — could go up or down. The important
metric is cluster coherence, not count.

### Test 3: Squirrel Query Retrieval
Ask "did we talk about squirrels?" — with contextual embeddings,
the squirrel messages embed with their animal-comparison context,
producing a centroid more likely to match animal-specific queries.
Compare score against v5.5.0 (where the cluster scored too low).

### Test 4: Decision Retrieval
Ask "what database did we decide on?" — the "yes, let's go with
PostgreSQL" message now embeds with context of the database
question, so it should cluster with the database discussion and
strengthen that cluster's centroid.

### Test 5: Query Embedding with Context
Verify that the query embedding also uses context. The user's
message is embedded with the previous conversation messages for
context. Check logs to confirm `build_contextual_text()` is called
for the query, not just `embed_text()` on raw content.

### Test 6: Bot Response Clustering
Check bot-dominated clusters after re-clustering:

```sql
SELECT c.label,
       count(*) as total,
       sum(CASE WHEN m.is_bot_author=1 THEN 1 ELSE 0 END) as bot,
       round(100.0 * sum(CASE WHEN m.is_bot_author=1 THEN 1 ELSE 0 END)
             / count(*), 1) as bot_pct
FROM cluster_messages cm
JOIN messages m ON m.id = cm.message_id
JOIN clusters c ON c.id = cm.cluster_id
WHERE c.channel_id = 1472003599985934560
GROUP BY c.id
ORDER BY bot_pct DESC LIMIT 10;
```

Expect fewer 100%-bot clusters compared to v5.5.0.

### Test 7: Incremental Assignment
Send a few new messages after re-embedding. Verify Tier 1
assignment still works — new messages get contextual embeddings
and assign to the correct cluster.

### Test 8: Performance
Backfill with context requires one SQLite read per message
(to fetch previous messages) plus the embedding API call.
Should complete in similar time to current backfill since the
SQLite queries are fast and the API calls dominate.

---

## Files Changed Summary

| File | Change |
|------|--------|
| `utils/embedding_store.py` or NEW `utils/embedding_context.py` | Add build_contextual_text(), get_previous_messages(), get_reply_context() |
| `utils/raw_events.py` | Use build_contextual_text() before embedding |
| `utils/context_manager.py` | Use build_contextual_text() for query embedding |
| `commands/debug_commands.py` | Update backfill to use contextual text, add --reembed flag |

---

## Documentation Updates

- `STATUS.md` — add v5.6.0 entry
- `HANDOFF.md` — update with context-prepended embedding strategy
- `README.md` — update embedding section
- `CLAUDE.md` — note that embeddings are contextual, not raw

---

## Constraints

1. Full files only
2. Increment version numbers
3. 250-line limit per file
4. `asyncio.to_thread()` for SQLite reads in context construction
5. Graceful degradation: if context fetch fails, embed raw content
6. All development on `claude-code` branch
