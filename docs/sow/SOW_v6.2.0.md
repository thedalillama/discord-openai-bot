# SOW v6.2.0 — SQLite FTS5 Hybrid Search + RRF Fusion
# Status: PROPOSED — awaiting approval
# Branch: claude-code
# Prerequisite: v6.1.0 (direct segment retrieval + top-K)
# Research basis: "Stop Chasing Higher Scores" retrieval analysis

---

## Problem Statement

v6.1.0 retrieval uses dense embeddings only. Keyword recall is 44%
because segment syntheses paraphrase original terms — "gorillas can
lift 5-10x their body weight" becomes "discussed primate strength
and capabilities." A user asking "what about gorillas?" depends
entirely on semantic proximity in the embedding space.

BM25 keyword matching solves this directly — it matches the word
"gorilla" in the raw source messages regardless of paraphrase.
Research shows combining BM25 with dense retrieval via Reciprocal
Rank Fusion improves nDCG@10 by 10-15% on standard benchmarks.

## Objective

1. Create an FTS5 full-text index over segment syntheses AND their
   source message content.
2. At query time, run BM25 alongside dense segment retrieval.
3. Fuse results via RRF (rank-based, score-agnostic).
4. Apply top-K to the fused ranking.
5. No changes to segmentation, clustering, or context injection.

---

## Design

### FTS5 Table: `schema/009.sql`

```sql
-- schema/009.sql
-- v6.2.0: FTS5 full-text search for hybrid retrieval

CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
    segment_id UNINDEXED,
    channel_id UNINDEXED,
    searchable_text,
    tokenize="porter unicode61"
);
```

The `searchable_text` column contains the segment synthesis
concatenated with all source message content. This ensures BM25
matches against both the resolved meaning AND the original words.

Example `searchable_text` for a segment:
```
Database Selection. absolutebeginner and Synthergy-GPT4 discussed
database options for the project. absolutebeginner asked about
PostgreSQL vs SQLite. Synthergy-GPT4 recommended PostgreSQL.
absolutebeginner agreed. --- absolutebeginner: Should we use
PostgreSQL or SQLite? Synthergy-GPT4: For your project I'd
recommend PostgreSQL... absolutebeginner: agreed
```

The `---` separator ensures BM25 doesn't cross-match between
synthesis and source messages in phrase queries.

### FTS5 Population

During `!summary create`, after segments are stored and embedded,
populate the FTS5 table. This happens in `segment_store.py` or a
new `fts_search.py` module.

```python
def populate_fts(channel_id):
    """Clear and rebuild FTS5 index for a channel's segments."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        # Clear existing entries for this channel
        conn.execute(
            "DELETE FROM segments_fts WHERE channel_id=?",
            (str(channel_id),))

        # Load segments with their source messages
        segments = conn.execute(
            "SELECT s.id, s.synthesis FROM segments "
            "WHERE s.channel_id=?", (channel_id,)).fetchall()

        for seg_id, synthesis in segments:
            msgs = conn.execute(
                "SELECT m.author_name, m.content "
                "FROM segment_messages sm "
                "JOIN messages m ON m.id=sm.message_id "
                "WHERE sm.segment_id=? ORDER BY sm.position",
                (seg_id,)).fetchall()
            msg_text = " ".join(
                f"{author}: {content}" for author, content in msgs
                if content and content.strip())
            searchable = f"{synthesis} --- {msg_text}"
            conn.execute(
                "INSERT INTO segments_fts "
                "(segment_id, channel_id, searchable_text) "
                "VALUES (?, ?, ?)",
                (seg_id, str(channel_id), searchable))

        conn.commit()
        logger.info(f"FTS5 index rebuilt: {len(segments)} segments "
                    f"ch:{channel_id}")
    finally:
        conn.close()
```

### BM25 Query

```python
def fts_search(query_text, channel_id, top_n=20):
    """Search segments via FTS5 BM25. Return ranked segment IDs.

    Args:
        query_text: raw user query string
        channel_id: Discord channel ID
        top_n: max results from BM25

    Returns:
        list of segment_id strings, ranked by BM25 relevance
        (best first). Empty list if no matches.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        # FTS5 MATCH syntax: double-quote the query to match as phrase,
        # or leave unquoted for OR matching across terms.
        # Use unquoted for broader recall.
        rows = conn.execute(
            "SELECT segment_id FROM segments_fts "
            "WHERE channel_id=? AND segments_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (str(channel_id), query_text, top_n)).fetchall()
        return [r[0] for r in rows]
    except Exception as e:
        logger.warning(f"FTS5 search failed ch:{channel_id}: {e}")
        return []
    finally:
        conn.close()
```

Note: FTS5 `rank` is negative (more negative = more relevant).
`ORDER BY rank` returns best matches first.

### Reciprocal Rank Fusion

```python
def rrf_fuse(dense_ranked, bm25_ranked, k=15, top_n=5):
    """Merge dense and BM25 rankings via Reciprocal Rank Fusion.

    RRF is score-agnostic — works on rank positions only. No need
    to normalize BM25 scores against cosine similarity.

    Args:
        dense_ranked: list of segment_ids from dense retrieval
            (best first)
        bm25_ranked: list of segment_ids from BM25 retrieval
            (best first)
        k: RRF constant (lower = more weight on top ranks;
            k=15 for small result sets)
        top_n: max results to return

    Returns:
        list of segment_ids, ranked by fused score (best first)
    """
    scores = {}
    for rank, seg_id in enumerate(dense_ranked, 1):
        scores[seg_id] = scores.get(seg_id, 0) + 1 / (k + rank)
    for rank, seg_id in enumerate(bm25_ranked, 1):
        scores[seg_id] = scores.get(seg_id, 0) + 1 / (k + rank)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [seg_id for seg_id, _ in ranked[:top_n]]
```

### Integration into `_retrieve_segment_context()`

The retrieval flow changes from:
```
query → embed → find_relevant_segments (dense only) → score-gap → inject
```

To:
```
query → embed → find_relevant_segments (dense) → ranked dense IDs
             → fts_search (BM25)                → ranked BM25 IDs
             → rrf_fuse(dense, bm25)             → fused segment IDs
             → fetch segment content             → inject
```

In `context_retrieval.py`, after embedding the query:

```python
# Dense retrieval (existing)
dense_segments = find_relevant_segments(
    query_vec, channel_id, top_k=RETRIEVAL_TOP_K * 2,
    floor=RETRIEVAL_FLOOR)
dense_ranked = [seg_id for seg_id, _, _, _ in dense_segments]

# BM25 retrieval (new)
bm25_ranked = fts_search(query_text, channel_id, top_n=20)

# Fuse
fused_ids = rrf_fuse(dense_ranked, bm25_ranked,
                      k=15, top_n=RETRIEVAL_TOP_K)

# Fetch content for fused results
# Score for receipt: use the dense score if available, else None
dense_scores = {sid: score for sid, _, _, score in dense_segments}
```

Score-gap detection is applied to the dense results before fusion
(unchanged from v6.1.0). The BM25 results participate in fusion
regardless — they provide the keyword signal that dense misses.

### When BM25 adds nothing

If BM25 returns empty (no keyword matches), fusion degrades
gracefully to dense-only — the `rrf_fuse` function simply returns
the dense ranking unchanged. No special handling needed.

### When dense adds nothing

If a channel has no segment embeddings (pre-v6), the cluster
rollback path fires as in v6.1.0. FTS5 is not consulted — it
depends on segments existing.

---

## New File: `utils/fts_search.py` v1.0.0

Functions:
- `populate_fts(channel_id)` — rebuild FTS5 index for a channel
- `clear_fts(channel_id)` — delete FTS5 entries for a channel
- `fts_search(query_text, channel_id, top_n=20)` — BM25 search
- `rrf_fuse(dense_ranked, bm25_ranked, k=15, top_n=5)` — RRF

~80 lines. All functions synchronous; callers use `asyncio.to_thread()`.

---

## Modified Files

| File | Version | Change |
|------|---------|--------|
| NEW `utils/fts_search.py` | v1.0.0 | FTS5 populate, search, RRF fusion |
| `schema/009.sql` | — | FTS5 virtual table |
| `utils/context_retrieval.py` | v1.7.0 | Hybrid retrieval: dense + BM25 + RRF fusion before segment content fetch |
| `utils/summarizer.py` | v4.2.0 | Call `populate_fts()` after segmentation in `!summary create` |
| `config.py` | v1.18.0 | Add `RRF_K` (default 15) |
| `STATUS.md` | v6.2.0 | Version entry |
| `HANDOFF.md` | — | Update retrieval architecture |
| `CLAUDE.md` | — | Update retrieval path |
| `README_ENV.md` | — | Document RRF_K |

### NOT changed
- `cluster_retrieval.py` — dense retrieval unchanged
- `cluster_engine.py` — clustering unchanged
- `segmenter.py` — segmentation unchanged
- `segment_store.py` — segment storage unchanged
- `bot.py` — no changes
- `response_handler.py` — citation pipeline unchanged
- `explain_commands.py` — receipt format unchanged (segments key
  already present from v6.1.0; scores come from dense retrieval)

---

## Testing

### Phase 1: Schema + FTS5
1. Restart bot — `schema/009.sql` applied, `segments_fts` table exists
2. Run `!summary create` — FTS5 index populated
3. Verify: `SELECT COUNT(*) FROM segments_fts;` matches segment count

### Phase 2: BM25 sanity check
4. Direct FTS5 query from Python:
```python
python3 -c "
import sqlite3
conn = sqlite3.connect('data/messages.db')
rows = conn.execute(
    \"SELECT segment_id FROM segments_fts \"
    \"WHERE channel_id='1472003599985934560' \"
    \"AND segments_fts MATCH 'gorilla' ORDER BY rank LIMIT 5\"
).fetchall()
print([r[0] for r in rows])
"
```
Should return segment IDs containing gorilla content.

### Phase 3: Benchmark
5. Run `retrieval_benchmark.py --verbose`
6. Compare against v6.1.0:

| Metric | v6.1.0 | Target |
|--------|--------|--------|
| Avg top score | 0.383 | maintain |
| Keyword recall | 44% | > 65% |
| Empty retrievals | 0% | 0% |
| Ch2 gorilla keywords | 100% | 100% |

The primary target is keyword recall improvement. Avg top score
should maintain or improve since RRF can surface segments that
dense retrieval ranked lower but BM25 ranked higher.

### Phase 4: Live test
7. Ask "what about gorillas?" in Discord — verify retrieval
8. Ask "PostgreSQL" — verify database segments retrieved
9. Run `!explain` — receipt should show segment scores
10. Verify citations work

### Phase 5: Regression
11. All commands work
12. Bot responds normally
13. Channels without segments still use rollback path

---

## Constraints

1. Full files only — no partial patches
2. Increment version numbers
3. 250-line file limit
4. All development on `claude-code` branch
5. FTS5 populated during `!summary create` only (not incremental)
6. BM25 failure degrades gracefully to dense-only
7. No new pip dependencies (FTS5 is built into SQLite)
8. Update all documentation alongside code changes
9. Run benchmark after implementation — report results
