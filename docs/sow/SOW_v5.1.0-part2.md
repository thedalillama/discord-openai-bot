# SOW v5.1.0 — Schema + HDBSCAN Clustering Core
# Part 2 of 2: Config, Commands, Testing, File Summary
# Status: APPROVED
# Branch: claude-code

---

## Modified: `config.py` v1.13.0

Add these configuration variables with environment variable overrides:

```python
# HDBSCAN clustering (v5.0.0)
CLUSTER_MIN_CLUSTER_SIZE = int(os.getenv('CLUSTER_MIN_CLUSTER_SIZE', '5'))
CLUSTER_MIN_SAMPLES = int(os.getenv('CLUSTER_MIN_SAMPLES', '3'))
UMAP_N_NEIGHBORS = int(os.getenv('UMAP_N_NEIGHBORS', '15'))
UMAP_N_COMPONENTS = int(os.getenv('UMAP_N_COMPONENTS', '5'))
```

---

## Modified: `commands/debug_commands.py` v1.4.0

Add `!debug clusters` command. This is the primary validation tool.

**Behavior**:
1. Load all message embeddings for the channel
2. Run `cluster_messages()` with default parameters
3. Store results to DB (so Phase 2 can read them)
4. Display diagnostic output to Discord

**Output format**:
```
ℹ️ **Cluster Analysis** (channel: #openclaw)
Messages: 540 total, 12 clusters, 47 noise (8.7%)
Largest cluster: 68 msgs (12.6%)

Cluster 0: 68 msgs (Mar 1 – Mar 15)
Cluster 1: 45 msgs (Mar 2 – Mar 10)
Cluster 2: 38 msgs (Mar 5 – Mar 12)
...
Noise: 47 msgs unassigned

Parameters: min_cluster_size=5, min_samples=3, umap_n=15, umap_d=5
```

Labels are not shown in Phase 1 since per-cluster LLM summarization
hasn't been implemented yet. Phase 2 will populate labels.

The output uses the ℹ️ prefix (informational/noise) per AGENT.md.

---

## Async Safety

All clustering operations must be wrapped in `asyncio.to_thread()`
since they involve CPU-bound numpy/sklearn work and SQLite operations.

```python
result = await asyncio.to_thread(cluster_messages, channel_id)
```

---

## What NOT to Change

- `utils/embedding_store.py` — reuse existing functions as-is
- `utils/raw_events.py` — message embedding on arrival unchanged
- `utils/summarizer.py` — summarization pipeline unchanged
- `utils/context_manager.py` — retrieval path unchanged
- `bot.py` — no changes
- All conversation providers — no changes
- All existing commands — no changes except `debug_commands.py`

---

## Testing Plan

### Test 1: Dependencies Install
```bash
pip install scikit-learn umap-learn --break-system-packages
python -c "from sklearn.cluster import HDBSCAN; from umap import UMAP; print('OK')"
```

### Test 2: Schema Migration
Restart bot. Verify `clusters` and `cluster_messages` tables exist.
Verify existing tables are unmodified.

### Test 3: Clustering on #openclaw (~540 messages)
Run `!debug clusters`. Expected:
- 8-15 clusters
- Noise ratio < 30% (after noise reduction)
- No single cluster > 50% of messages
- Clustering completes in < 5 seconds

### Test 4: Cluster Coherence (Manual Spot-Check)
Pick 3 clusters. For each, query `cluster_messages` joined with
`messages` to see the actual message content. Verify messages in each
cluster relate to the same topic. Messages about gorillas should be
together, not mixed with database decisions.

### Test 5: Clustering on Large Channel (~1,600 messages)
Run `!debug clusters` on the larger channel. Expected:
- 15-40 clusters
- Clustering completes in < 10 seconds
- Reasonable distribution — no single mega-cluster

### Test 6: Parameter Sensitivity
Run `!debug clusters` with different .env overrides:
- `CLUSTER_MIN_CLUSTER_SIZE=3` (more clusters, less noise)
- `CLUSTER_MIN_CLUSTER_SIZE=10` (fewer clusters, more noise)
- `CLUSTER_MIN_SAMPLES=5` (more noise)
Document the effect. Select best defaults.

### Test 7: Edge Case — Channel With Few Messages
Run on a channel with < 10 messages. Should return gracefully
(not enough messages to cluster) without errors.

### Test 8: Edge Case — Channel With No Embeddings
Run on a channel where `!debug backfill` hasn't been run. Should
return gracefully with a clear message.

### Test 9: Existing Bot Functionality
After deploying Phase 1, verify:
- Bot responds normally to messages
- `!summary create` still works (v4.1.x pipeline)
- Semantic retrieval still works
- No errors in logs from the new schema or imports

---

## Files Changed Summary

| File | From | To | Change |
|------|------|----|--------|
| `schema/005.sql` | NEW | v1.0.0 | clusters + cluster_messages tables |
| `utils/cluster_store.py` | NEW | v1.0.0 | UMAP + HDBSCAN clustering, CRUD, diagnostics |
| `config.py` | v1.12.6 | v1.13.0 | Add clustering config vars |
| `commands/debug_commands.py` | v1.3.0 | v1.4.0 | Add `!debug clusters` command |

If `cluster_store.py` exceeds 250 lines, split into:
- `utils/cluster_engine.py` — UMAP + HDBSCAN pipeline, noise reduction
- `utils/cluster_store.py` — SQLite CRUD, storage, diagnostics

---

## Documentation Updates

Update with every commit:
- `STATUS.md` — add v5.1.0 entry
- `HANDOFF.md` — update current status and what just happened
- `README.md` — add cluster tables to schema section
- `README_ENV.md` — add new env vars
- `CLAUDE.md` — add clustering architecture notes
- `AGENT.md` — update architecture context section

---

## Constraints

1. **Full files only** — no partial diffs or patches
2. **Increment version numbers** in file heading comments
3. **250-line limit per file** — split if needed
4. **ℹ️ prefix** on all `!debug clusters` output
5. **asyncio.to_thread()** for all CPU-bound and SQLite operations
6. **Do not modify** the existing summarization or retrieval paths
7. **All development on `claude-code` branch**
8. **Discuss before coding** — get approval before implementing
