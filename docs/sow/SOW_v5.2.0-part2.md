# SOW v5.2.0 — Per-Cluster LLM Summarization
# Part 2 of 2: Storage, Commands, Testing, File Summary
# Status: PROPOSED — awaiting approval
# Branch: claude-code

---

## Storage: Updating `clusters` Table

After each successful `summarize_cluster()` call, update the existing
cluster row with the LLM-generated fields:

```python
def update_cluster_summary(cluster_id, label, summary, status,
                           decisions_json, key_facts_json,
                           action_items_json, open_questions_json):
    """Update a cluster with LLM-generated summary fields.

    The structured fields (decisions, key_facts, etc.) are stored as
    JSON strings in a new 'structured_data' column, or serialized
    into the existing 'summary' column as a JSON blob.
    """
```

**Design choice**: Store the per-cluster structured data (decisions,
key_facts, action_items, open_questions) as a JSON blob in the
`clusters.summary` column. The `clusters.label` column gets the
LLM-generated label. The `clusters.status` column gets "active" or
"archived". This avoids a schema migration — the `summary` column
already exists as TEXT and can hold JSON.

The summary column format after v5.2.0:
```json
{
    "text": "1-3 sentence summary...",
    "decisions": [...],
    "key_facts": [...],
    "action_items": [...],
    "open_questions": [...]
}
```

v5.3.0 will read these when generating the cross-cluster overview.

---

## New Helper: `utils/cluster_store.py` Updates

Add to `cluster_store.py` (v5.1.0 module):

```python
def get_cluster_message_ids(cluster_id):
    """Return list of message_ids for a cluster, ordered by created_at."""

def get_clusters_for_channel(channel_id):
    """Return list of cluster dicts: id, label, summary, status,
    message_count, first_message_at, last_message_at.
    Ordered by message_count descending."""

def update_cluster_label_summary(cluster_id, label, summary_json, status):
    """Update label, summary, and status for a cluster after LLM pass."""
```

Also reuse from `utils/message_store.py`:

```python
def get_messages_by_ids(message_ids):
    """Return (id, author_name, content, created_at) for given IDs.
    Ordered by created_at ascending."""
```

If `get_messages_by_ids()` doesn't exist in `message_store.py`, add
it. It's a simple SELECT with an IN clause.

---

## Modified: `commands/debug_commands.py` v1.5.0

Add `!debug summarize_clusters` command for validation:

```
!debug summarize_clusters
```

**Behavior**:
1. Get stored clusters for the channel (from v5.1.0)
2. If no clusters exist, prompt user to run `!debug clusters` first
3. Call `summarize_all_clusters()` — LLM call for each cluster
4. Display results:

```
ℹ️ **Cluster Summarization** (channel: #openclaw)
Processing 56 clusters...

Cluster 0 (70 msgs): "Bonobo References" — archived
Cluster 1 (44 msgs): "Bot Knowledge Denials" — archived
Cluster 6 (21 msgs): "Animal Strength and Speed Comparisons" — archived
Cluster 7 (23 msgs): "Database Selection: PostgreSQL to SQLite" — active
...

Processed: 56 clusters, 0 failures
Tokens: ~X input, ~Y output
```

**Important**: This command makes 56 Gemini API calls (one per cluster).
It will take 1-3 minutes and cost a small amount. Log progress every
5 clusters so the user knows it's working.

Output uses ℹ️ prefix. Paginate if output exceeds 2000 chars (split
across multiple messages, same as v5.1.0 fix).

---

## Error Handling

- If a Gemini call fails for a specific cluster, log the error and
  continue to the next cluster. Don't abort the entire run.
- If the JSON response fails to parse, log the raw response and skip.
- Retry once on failure before skipping (Gemini transient errors).
- Track and report failure count in the summary output.

---

## Async Safety

Each Gemini call goes through the existing `generate_ai_response()`
which already uses `run_in_executor()`. The `summarize_all_clusters()`
function is async and awaits each call sequentially (not parallel —
avoid Gemini rate limits on Flash Lite).

SQLite updates via `asyncio.to_thread()`.

---

## What NOT to Change

- `utils/summarizer.py` — unchanged (v5.3.0 wires this in)
- `utils/context_manager.py` — unchanged (v5.4.0)
- `utils/summary_display.py` — unchanged (v5.3.0)
- `utils/cluster_engine.py` — unchanged
- `bot.py` — unchanged
- All conversation providers — unchanged

---

## Testing Plan

### Test 1: Single Cluster Summarization
Run `!debug summarize_clusters` on #openclaw. Pick 5 clusters and
verify:
- Labels are concise (3-8 words) and descriptive
- Summaries accurately describe the cluster content
- Status is reasonable (ongoing topics = active, concluded = archived)

### Test 2: Structured Field Extraction
For clusters with known content (database decisions, animal facts),
verify:
- `decisions` contains actual decisions (e.g., "Use SQLite")
- `key_facts` contains durable facts (e.g., "PostgreSQL supports JSONB")
- `action_items` has tasks if any were assigned
- `open_questions` has unresolved questions
- `source_message_ids` reference valid M-labels

### Test 3: Noise Cluster Handling
Clusters of bot filler, connection testing, or repeated content
should produce:
- Short/trivial summaries
- Status "archived"
- Few or no structured items
- No hallucinated decisions or action items

### Test 4: Large Cluster Truncation
If any cluster has > 50 messages, verify:
- Only the 50 most recent are sent to Gemini
- The prefix note is included
- Summary still captures the topic accurately

### Test 5: Cost Check
After running on all 56 clusters, check total token usage.
Expected: ~500-5000 input tokens per cluster × 56 = ~28K-280K
input tokens total. At Gemini Flash Lite pricing this should be
well under $0.10.

### Test 6: Failure Recovery
Kill the bot mid-run (or simulate a Gemini error). Re-run
`!debug summarize_clusters`. Verify it processes all clusters
(including ones that were already summarized — it overwrites).

### Test 7: Existing Functionality
Verify bot responds normally, existing summary pipeline works,
semantic retrieval works. No regressions from v5.2.0 code.

---

## Files Changed Summary

| File | From | To | Change |
|------|------|----|--------|
| `utils/cluster_summarizer.py` | NEW | v1.0.0 | Per-cluster Gemini summarization, prompt, schema |
| `utils/cluster_store.py` | v1.0.0 | v1.1.0 | Add get_cluster_message_ids, get_clusters_for_channel, update_cluster_label_summary |
| `commands/debug_commands.py` | v1.4.0 | v1.5.0 | Add `!debug summarize_clusters` |
| `utils/message_store.py` | v1.2.0 | v1.3.0 | Add get_messages_by_ids (if not present) |

---

## Documentation Updates

Update with every commit:
- `STATUS.md` — add v5.2.0 entry
- `HANDOFF.md` — update current status
- `README.md` — add cluster summarization to architecture section
- `CLAUDE.md` — add per-cluster summarization notes

---

## Constraints

1. **Full files only** — no partial diffs or patches
2. **Increment version numbers** in file heading comments
3. **250-line limit per file** — split if needed
4. **ℹ️ prefix** on all command output
5. **Sequential Gemini calls** — no parallel requests
6. **Do not modify** summarizer.py or context_manager.py
7. **All development on `claude-code` branch**
8. **Discuss before coding** — get approval before implementing
