# SOW v5.5.0 — Cluster-Based Retrieval Integration
# Part 2 of 2: Testing, File Summary, Documentation
# Status: PROPOSED — awaiting approval
# Branch: claude-code

---

## Testing Plan

### Test 1: Basic Retrieval — Known Topics
Ask the bot questions about topics with known clusters:

- "did we discuss gorillas?" — expect the animal/evolution cluster(s)
  to be retrieved, with messages about gorilla strength, diet, etc.
- "what database are we using?" — expect the database cluster, with
  messages about PostgreSQL, SQLite, Redis decisions.
- "tell me about airplanes" — expect the aerodynamics cluster.

Check logs to verify:
```bash
sudo journalctl -u discord-bot --since "1 min ago" | grep -i "cluster\|retrieved\|score"
```

Verify the correct cluster was selected and its messages were
injected into the context.

### Test 2: Retrieval Scores and Threshold
Check that `RETRIEVAL_MIN_SCORE` (0.25) is filtering low-relevance
clusters. Ask about something partially related and verify logs
show cluster scores. The right cluster should score well above
threshold; unrelated clusters should score below.

### Test 3: Fallback Still Works
Ask about something never discussed (e.g., "what's our policy on
quantum computing?"). Neither cluster retrieval nor message fallback
should return results. The bot should correctly say it hasn't been
discussed, or respond from training knowledge. Verify in logs that
fallback fired and returned empty.

### Test 4: No Duplicate Messages
Recent messages (last 5 in conversation) should NOT appear in the
retrieved cluster messages. The `exclude_ids` filtering prevents
this. Verify by checking the context block in logs — recent messages
should appear only in the conversation section, not duplicated in
the retrieved section.

### Test 5: Timestamps Preserved
Retrieved cluster messages should have `[YYYY-MM-DD]` prefixes.
Today's date should appear at the top of the context block. Verify
in logs.

### Test 6: Token Budget Respected
If a cluster has many messages, the token budget should stop
injection before exceeding the limit. Ask about a large cluster
topic and verify in logs that the budget trimmer stopped mid-cluster
or skipped a cluster due to budget exhaustion.

### Test 7: Compare Against v4.x Retrieval
For the same questions tested in v4.0.0 validation:
- "what have we said about gorillas?" — should retrieve gorilla
  messages (v4.0.0 retrieved strength + diet + bachelor party toast)
- "how are we related to them?" — should retrieve evolutionary
  relationship messages
- "who else did we say humans are closely related to?" — should
  retrieve bonobos/chimps

Quality should be comparable or better since clusters have direct
membership (no similarity-based linkage approximation).

### Test 8: Performance
Retrieval latency should be comparable to v4.x:
- One `embed_text()` API call (~100-200ms)
- Centroid comparison (microseconds for 60 clusters)
- SQLite queries for cluster messages (~1ms)
- Total: <300ms added to response time

### Test 9: Edge Cases
- Channel with no clusters (never ran `!summary create`): should
  fall through to message fallback, then to full summary injection.
  No errors.
- Channel with clusters but no summary in `channel_summaries`:
  always-on context is empty, but retrieval should still work.

### Test 10: Existing Functionality
- `!summary create` still works
- `!summary update` still works
- `!summary` display still works
- `!summary clear` still works
- Bot responds to non-addressed messages normally

---

## Files Changed Summary

| File | From | To | Change |
|------|------|----|--------|
| `utils/context_manager.py` | current | +1 | Swap topic imports for cluster imports; replace find_relevant_topics/get_topic_messages with find_relevant_clusters/get_cluster_messages |
| `utils/cluster_store.py` | current | +1 | Add find_relevant_clusters() and get_cluster_messages() if not already present |

### Potentially Unchanged
- `utils/embedding_store.py` — topic functions remain (unused but
  retained for rollback). `embed_text()` and `find_similar_messages()`
  still used.
- `utils/summary_display.py` — unchanged
- `bot.py` — unchanged
- All providers — unchanged
- All other commands — unchanged

---

## Documentation Updates

- `STATUS.md` — add v5.5.0 entry
- `HANDOFF.md` — update: v5.5.0 complete, full v5 pipeline live,
  retrieval now uses cluster centroids
- `README.md` — update retrieval section to describe cluster-based
  retrieval replacing topic-based
- `CLAUDE.md` — update architecture context
- `AGENT.md` — update architecture context: retrieval now uses
  `find_relevant_clusters` / `get_cluster_messages` from
  `cluster_store.py`; topic functions in `embedding_store.py`
  retained but unused

---

## Constraints

1. Full files only — no partial diffs
2. Increment version numbers
3. 250-line limit per file
4. Do NOT delete topic functions from `embedding_store.py`
5. Do NOT change the context block framing text (the LLM prompt)
6. Do NOT change config variables or thresholds
7. `asyncio.to_thread()` for all SQLite operations
8. All development on `claude-code` branch
