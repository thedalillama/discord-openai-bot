# SOW v5.3.0 — Cross-Cluster Overview + Pipeline Wiring
# Part 2 of 2: Pipeline, Routing, Commands, Testing, File Summary
# Status: PROPOSED — awaiting approval
# Branch: claude-code

---

## Pipeline Orchestrator

Add `run_cluster_pipeline()` to `cluster_summarizer.py` (or a new
`utils/cluster_pipeline.py` if the file would exceed 250 lines):

```python
async def run_cluster_pipeline(channel_id, provider):
    """Full v5 pipeline: cluster → summarize → overview → store.

    Steps:
    1. Run UMAP + HDBSCAN clustering (from cluster_store/cluster_engine)
    2. Clear old clusters, store new ones
    3. Summarize each cluster with Gemini (from v5.2.0)
    4. Generate cross-cluster overview with Gemini
    5. Translate overview to v4.x-compatible summary JSON
    6. Save to channel_summaries via save_channel_summary()
    7. Return result dict with stats

    Returns:
        {
            "cluster_count": int,
            "noise_count": int,
            "messages_processed": int,
            "overview_generated": bool,
            "error": str or None,
        }
    """
```

This is the single entry point that v5.3.0's summarizer routing calls.

---

## Summarizer Routing: `utils/summarizer.py` v3.0.0

The key change: `summarize_channel()` routes to the cluster pipeline
instead of the three-pass Secretary/Structurer/Classifier pipeline.

```python
async def summarize_channel(channel_id, batch_size=None):
    """Generate or update the structured summary for a channel.

    v5.3.0: Routes to cluster-based pipeline. The v4.x three-pass
    pipeline (summarizer_authoring.py) is no longer called but
    remains in the codebase for rollback safety.
    """
    from utils.cluster_summarizer import run_cluster_pipeline
    from ai_providers import get_provider
    from config import SUMMARIZER_PROVIDER

    provider = get_provider(SUMMARIZER_PROVIDER)
    result = await run_cluster_pipeline(channel_id, provider)
    return result
```

The `batch_size` parameter is accepted but ignored — clustering
processes all messages at once (full re-cluster). The parameter
remains for API compatibility with callers.

**Important**: The existing `_incremental_loop()`, `_get_unsummarized_
messages()`, and `_process_response()` functions remain in the file
but are no longer called. Do NOT delete them — they're the rollback
path if v5 has issues in production.

---

## Updated: `commands/summary_commands.py` v2.3.0

The `!summary create` command already calls `summarize_channel()`.
Since we're changing the router in `summarizer.py`, the command
itself needs minimal changes. Update the result handling to display
cluster-specific stats:

```
ℹ️ Summary created for #openclaw
Pipeline: cluster-v5
Clusters: 56 (2 noise messages)
Messages processed: 741
```

The `!summary` display command reads from `channel_summaries` which
now contains the v5 JSON. The existing display code should work
since we're using compatible field names. Verify this during testing.

`!summary clear` continues to call `delete_channel_summary()` —
unchanged. It should also clear clusters:

```python
# In !summary clear handler, add:
from utils.cluster_store import clear_channel_clusters
clear_channel_clusters(ctx.channel.id)
```

---

## Remove `!debug clusters` and `!debug summarize_clusters`

These were development/validation commands for v5.1.0 and v5.2.0.
Now that `!summary create` runs the full pipeline, they are redundant.

**Keep them** but document them as diagnostic-only. They're useful for
debugging cluster quality without regenerating the full summary.

---

## Error Handling / Fail-Safe

If the cluster pipeline fails at any point, `summarize_channel()`
should catch the exception and return an error result. The existing
summary in `channel_summaries` is NOT deleted on failure — the bot
continues using whatever summary was previously stored.

```python
try:
    result = await run_cluster_pipeline(channel_id, provider)
except Exception as e:
    logger.error(f"Cluster pipeline failed: {e}")
    return {"error": str(e), "messages_processed": 0}
```

---

## What NOT to Change

- `utils/summary_display.py` — unchanged (compatible field names)
- `utils/context_manager.py` — unchanged (reads channel_summaries)
- `utils/embedding_store.py` — unchanged
- `utils/raw_events.py` — unchanged
- `bot.py` — unchanged
- All conversation providers — unchanged
- `utils/summarizer_authoring.py` — NOT called, but NOT deleted

---

## Testing Plan

### Test 1: Full Pipeline via `!summary create`
Run `!summary create` on #openclaw. Verify:
- Clustering runs (logs show UMAP + HDBSCAN)
- Per-cluster summarization runs (logs show Gemini calls)
- Overview generation runs (one final Gemini call)
- Summary stored in channel_summaries
- Output shows cluster-v5 pipeline stats

### Test 2: Always-On Context Compatibility
After `!summary create`, send a regular message to the bot. Verify:
- Bot responds normally (no errors in logs)
- `format_always_on_context()` produces valid output
- Overview, key facts, action items, open questions are injected

Check logs for the context block:
```bash
sudo journalctl -u discord-bot --since "1 min ago" | grep "Context block"
```

### Test 3: Summary Display
Run `!summary` to view the stored summary. Verify:
- Overview is shown
- Key facts are listed
- Decisions are listed
- Formatting matches v4.x display quality

### Test 4: Summary Clear
Run `!summary clear`. Verify clusters AND channel_summaries are
deleted. Run `!summary` — should say "no summary available."

### Test 5: Re-run Idempotency
Run `!summary create` twice. Second run should produce identical
results (UMAP random_state=42 ensures reproducibility). No stale
clusters accumulate.

### Test 6: Existing Retrieval Still Works
After `!summary create`, ask the bot "did we discuss gorillas?"
The v4.x topic retrieval path still works because `_retrieve_topic_
context()` reads from `topics` table (unchanged). v5.4.0 will swap
this to cluster retrieval.

Note: If topic retrieval is empty (because `!summary create` no
longer populates the topics table), the fallback to
`find_similar_messages()` fires. This is acceptable — retrieval
quality may temporarily degrade between v5.3.0 and v5.4.0 but the
bot will still respond with relevant context via message fallback.

### Test 7: Cost Check
The full pipeline makes: 56 cluster summarization calls + 1 overview
call = 57 Gemini calls. Compare total token usage against the v4.x
pipeline (3 calls but much larger inputs). Expected: comparable or
cheaper total cost.

---

## Files Changed Summary

| File | From | To | Change |
|------|------|----|--------|
| `utils/cluster_summarizer.py` | v1.0.0 | v1.1.0 | Add generate_overview(), run_cluster_pipeline(), translate_to_channel_summary() |
| `utils/summarizer.py` | v2.2.0 | v3.0.0 | Route to cluster pipeline |
| `commands/summary_commands.py` | v2.2.0 | v2.3.0 | Updated result display, clear clusters on !summary clear |

If `cluster_summarizer.py` exceeds 250 lines, split overview logic
into `utils/cluster_overview.py`.

---

## Documentation Updates

- `STATUS.md` — add v5.3.0 entry
- `HANDOFF.md` — update: v5.3.0 complete, !summary create uses
  cluster pipeline, v4.x pipeline retained but unused
- `README.md` — update summarization pipeline description
- `CLAUDE.md` — update pipeline architecture notes

---

## Constraints

1. **Full files only** — no partial diffs or patches
2. **Increment version numbers** in file heading comments
3. **250-line limit per file** — split if needed
4. **Do not delete** v4.x pipeline files (rollback safety)
5. **Do not modify** context_manager.py or summary_display.py
6. **All development on `claude-code` branch**
