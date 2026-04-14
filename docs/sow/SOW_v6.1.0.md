# SOW v6.1.0 — Direct Segment Retrieval + Top-K Selection
# Status: PROPOSED — awaiting approval
# Branch: claude-code
# Prerequisite: v6.0.0 (segmentation pipeline)
# Research basis: "Stop Chasing Higher Scores" retrieval analysis

---

## Problem Statement

v6.0.0 retrieval queries 15 cluster centroids instead of 150
individual segment embeddings. A centroid is the mean of its member
segment vectors — when a cluster contains segments about database
selection, hosting, and rate limiting, the centroid sits equidistant
from all three and matches none precisely. This is the primary cause
of the score drop from 0.377 (v5.13 baseline) to 0.325 (v6.0.0).

At 150 segments, brute-force cosine similarity takes <1ms in NumPy.
Centroid-based indexing exists for 100K+ vector corpora; at our
scale it adds complexity while removing precision.

## Objective

1. Query all segment embeddings directly instead of cluster centroids.
2. Replace fixed threshold (`RETRIEVAL_MIN_SCORE`) with top-K
   selection + score-gap detection.
3. Map retrieved segments back to clusters for context injection.
4. Preserve citation, `!explain`, and rollback paths.

---

## Design

### New retrieval function: `find_relevant_segments()`

```python
def find_relevant_segments(query_embedding, channel_id, top_k=5,
                           floor=0.15):
    """Score query against all segment embeddings. Return top-K.

    Args:
        query_embedding: query vector (list or np.array)
        channel_id: Discord channel ID
        top_k: max segments to return
        floor: absolute minimum score (below this, never return)

    Returns:
        list of (segment_id, topic_label, synthesis, score) tuples,
        score descending. Only segments above floor included.
    """
```

Implementation: load all segment embeddings from `segments` table
(`SELECT id, topic_label, synthesis, embedding FROM segments WHERE
channel_id=? AND embedding IS NOT NULL`), compute cosine similarity
against each, sort descending, apply floor filter, return top-K.

This replaces `find_relevant_clusters()` on the retrieval hot path.
`find_relevant_clusters()` is kept for `!debug clusters` and rollback.

### Score-gap detection (optional cutoff)

After top-K selection, find the largest gap between adjacent sorted
scores. If the gap exceeds a threshold (e.g., 0.08), cut the list
there. This provides an adaptive relevance boundary without a fixed
absolute threshold.

```python
def _apply_score_gap(results, gap_threshold=0.08):
    """Cut results at the largest score gap if it exceeds threshold."""
    if len(results) <= 1:
        return results
    gaps = [(results[i][3] - results[i+1][3], i+1)
            for i in range(len(results) - 1)]
    max_gap, cut_idx = max(gaps, key=lambda x: x[0])
    if max_gap >= gap_threshold:
        return results[:cut_idx]
    return results
```

Score-gap detection is applied after top-K. If no significant gap
exists, all top-K results are returned. Configurable via
`RETRIEVAL_SCORE_GAP` env var (default 0.08).

### Segment-to-cluster mapping for context injection

Retrieved segments need their source messages for citation. The
existing `get_cluster_content()` walks cluster → segments → messages.
For direct segment retrieval, we need the reverse: segment → messages.

New function in `segment_store.py`:

```python
def get_segment_with_messages(segment_id, exclude_ids=None):
    """Return segment synthesis + source messages for a single segment.

    Returns:
        {"segment_id", "topic_label", "synthesis",
         "messages": [(msg_id, author, content, created_at), ...]}
    """
```

This is the per-segment version of `get_cluster_content()`. The
context injection format is unchanged:

```
[Topic: label]
Summary: synthesis text

Source messages:
[N] [date] author: content
```

### Changes to `_retrieve_cluster_context()`

Rename to `_retrieve_segment_context()`. The function:

1. Embeds the query via `embed_query_with_smart_context()` (unchanged)
2. Calls `find_relevant_segments()` instead of `find_relevant_clusters()`
3. Applies score-gap detection
4. For each retrieved segment: calls `get_segment_with_messages()`
5. Builds context text with synthesis + source messages + [N] labels
6. Builds citation_map from source messages (unchanged)
7. Applies token budget (unchanged — same partial injection logic)
8. Returns (context_text, tokens_used, receipt, citation_map)

Rollback: if no segments exist (pre-v6 channel), falls back to
`find_relevant_clusters()` + `get_cluster_messages()` as today.

### Receipt changes

The receipt dict changes from cluster-centric to segment-centric:

```python
receipt = {
    "query": query_text,
    "embedding_path": embedding_path,
    "retrieved_segments": [
        {"segment_id": seg_id, "topic_label": label,
         "score": score, "message_count": n, "tokens": t}
    ],
    "segments_below_floor": [...],
    "score_gap_applied": True/False,
    "fallback_used": False,
    "fallback_messages": 0,
}
```

`!explain` display updated to show segments instead of clusters.

---

## Config Changes

```python
# config.py v1.17.0

# RETRIEVAL_TOP_K: max segments (was clusters) returned per query.
RETRIEVAL_TOP_K = int(os.environ.get('RETRIEVAL_TOP_K', 5))

# RETRIEVAL_FLOOR: absolute minimum score. Segments below this are
# never returned regardless of top-K. Set low — top-K and score-gap
# are the primary filters. (SOW v6.1.0)
RETRIEVAL_FLOOR = float(os.environ.get('RETRIEVAL_FLOOR', 0.15))

# RETRIEVAL_SCORE_GAP: minimum gap between adjacent scores to trigger
# cutoff. Set to 0 to disable score-gap detection. (SOW v6.1.0)
RETRIEVAL_SCORE_GAP = float(
    os.environ.get('RETRIEVAL_SCORE_GAP', 0.08))

# RETRIEVAL_MIN_SCORE: retained for rollback path and incremental
# cluster assignment. Not used on the primary segment retrieval path.
```

---

## Files Changed

| File | Version | Change |
|------|---------|--------|
| `utils/cluster_retrieval.py` | v1.2.0 | Add `find_relevant_segments()`, keep `find_relevant_clusters()` for rollback/debug |
| `utils/segment_store.py` | v1.1.0 | Add `get_segment_with_messages()` |
| `utils/context_retrieval.py` | v1.6.0 | `_retrieve_segment_context()` replaces `_retrieve_cluster_context()`, calls segment retrieval, score-gap detection |
| `commands/explain_commands.py` | v1.2.0 | Update `format_receipt()` for segment-based receipts |
| `config.py` | v1.17.0 | Add `RETRIEVAL_FLOOR`, `RETRIEVAL_SCORE_GAP` |
| `README_ENV.md` | — | Document new config vars |
| `STATUS.md` | v6.1.0 | Version entry |
| `HANDOFF.md` | — | Update retrieval architecture |
| `CLAUDE.md` | — | Update retrieval path description |

### NOT changed
- `cluster_engine.py` — clustering unchanged
- `cluster_store.py` — cluster storage unchanged
- `segmenter.py` — segmentation unchanged
- `segment_store.py` — only adds one new function
- `summarizer.py` — pipeline routing unchanged
- `bot.py` — no changes
- `response_handler.py` — citation pipeline unchanged
- `citation_utils.py` — unchanged

---

## Testing

### Phase 1: Import + startup
1. `python -c "import bot"` — clean imports
2. Restart bot — no errors in journal

### Phase 2: Retrieval quality
3. Run `retrieval_benchmark.py --verbose` on both channels
4. Compare against v6.0.0 baseline:

| Metric | v6.0.0 | Target |
|--------|--------|--------|
| Avg top score | 0.325 | > 0.45 |
| Keyword recall | 50% | ≥ 50% |
| Empty retrievals | 8% | 0% |
| Ch2 database top score | 0.519 | > 0.60 |
| Ch2 abstract queries | ~0.26 | > 0.35 |

### Phase 3: Score-gap detection
5. Check logs for score-gap cutoff behavior — verify it's cutting
   at natural boundaries, not chopping relevant results
6. If too aggressive (cutting relevant segments), raise
   `RETRIEVAL_SCORE_GAP` to 0.10 or 0.12

### Phase 4: Context injection
7. Ask a question in Discord that triggers retrieval
8. Verify response includes relevant content from retrieved segments
9. Verify citations ([N] markers + Sources footer) work
10. Run `!explain` — verify segment-based receipt displays correctly

### Phase 5: Rollback
11. Test on a channel that hasn't run `!summary create` since v6.0.0
    (no segments) — should fall back to cluster centroid retrieval
12. Verify fallback produces usable results

### Phase 6: Regression
13. All commands work: `!summary`, `!explain`, `!status`, `!debug`
14. Bot responds normally to messages
15. Citations work with Anthropic provider

---

## Constraints

1. Full files only — no partial patches
2. Increment version numbers
3. 250-line file limit
4. All development on `claude-code` branch
5. Keep `find_relevant_clusters()` for rollback and debug
6. Keep `RETRIEVAL_MIN_SCORE` for rollback path
7. Citations reference individual messages, not segments
8. Score-gap detection is optional (disabled when gap=0)
9. Update all documentation alongside code changes
10. Run benchmark after implementation — report results
