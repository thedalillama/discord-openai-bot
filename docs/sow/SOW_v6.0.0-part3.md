# SOW v6.0.0 — Conversation Segmentation Pipeline
# Part 3 of 3: File Changes, Testing, Success Criteria
# Status: IMPLEMENTED (2026-04-13)
# Branch: claude-code

---

## New Files

### `utils/segmenter.py` v1.0.0

Core segmentation + synthesis module.

Functions:
- `segment_and_synthesize(messages, batch_size=500)` — main entry
  point. Splits messages into batches, calls Gemini per batch with
  overlap handling, returns list of segment dicts.
- `_build_segmentation_prompt(messages)` — formats messages for the
  combined segmentation+synthesis Gemini call.
- `_parse_segments(response, messages)` — validates Gemini output:
  ordered, non-overlapping, complete coverage. Returns parsed
  segment list or raises ValueError.
- `_fallback_time_gap(messages, gap_minutes=30)` — time-gap
  segmentation when LLM fails. Returns segments with concatenated
  message text as synthesis (no meaning resolution).
- `SEGMENTATION_SYSTEM_PROMPT` — the system prompt from Part 1.
- `SEGMENTATION_SCHEMA` — the JSON schema from Part 1.

Dependencies: Gemini provider (existing), message_store (existing).

### `utils/segment_store.py` v1.0.0

Segment CRUD and query functions.

Functions:
- `store_segments(channel_id, segments)` — bulk insert segments +
  segment_messages. Generates IDs as `seg-{channel_id}-{seq}`.
- `clear_channel_segments(channel_id)` — delete all segments +
  segment_messages for a channel.
- `get_segment_embeddings(channel_id)` — returns (id, embedding)
  pairs for UMAP input.
- `get_segments_by_ids(segment_ids)` — returns segment dicts for
  cluster summarizer input.
- `get_cluster_content(cluster_id, exclude_ids=None)` — the
  cluster → segments → messages walk for retrieval + citation.
- `store_segment_embedding(segment_id, embedding)` — store packed
  embedding blob.
- `get_segment_count(channel_id)` — count for diagnostics.

All functions synchronous; callers use `asyncio.to_thread()`.

---

## Modified Files

### `utils/cluster_engine.py` v1.1.0
- ADD: `cluster_segments(channel_id, ...)` — UMAP + HDBSCAN on
  segment embeddings. Same logic as `cluster_messages()` but reads
  from `segments` table via `get_segment_embeddings()`.
- KEEP: `cluster_messages()` — retained for rollback.

### `utils/cluster_store.py` v2.1.0
- MODIFY: `run_clustering()` — add `use_segments=True` parameter.
  When True, calls `cluster_segments()` and stores results in
  `cluster_segments`. When False, uses existing message path.
- ADD: `store_cluster_segments(cluster_id, segment_ids)` — insert
  into `cluster_segments` junction table.
- ADD: `clear_channel_cluster_segments(channel_id)` — cleanup.
- KEEP: All existing message-based functions for rollback.

### `utils/cluster_summarizer.py` v1.1.0
- MODIFY: `summarize_cluster()` — add `use_segments=True` parameter.
  When True, loads segment syntheses instead of raw messages for the
  Gemini prompt. M-labels use segment topic_label prefix.

### `utils/cluster_retrieval.py` v1.1.0
- ADD: `get_cluster_content()` — segment-aware retrieval function
  (delegates to `segment_store.get_cluster_content()`).
- KEEP: `get_cluster_messages()` for rollback.

### `utils/context_retrieval.py` v1.5.0
- MODIFY: `_retrieve_cluster_context()` — call `get_cluster_content()`
  instead of `get_cluster_messages()`. Build context text with
  synthesis + source messages format. Citation map built from source
  messages (unchanged citation UX).
- Handle synthesis-only mode when budget is tight.

### `utils/summarizer.py` v4.1.0
- MODIFY: `!summary create` routing — add segmentation steps before
  clustering: call `segment_and_synthesize()`, store segments, embed
  syntheses, then proceed to clustering with `use_segments=True`.

### `commands/cluster_commands.py` v1.4.0
- ADD: `!debug segments` command — show segment count, avg size,
  sample segments with topic labels and synthesis previews.
- MODIFY: `!debug reembed` — add segment awareness: after reembed,
  note that `!summary create` is needed to rebuild segments.

### `schema/008.sql` (new)
- As specified in Part 1: segments, segment_messages, cluster_segments
  tables with indexes.

### Config + docs
- `config.py` v1.16.0 — add `SEGMENT_BATCH_SIZE` (default 500),
  `SEGMENT_OVERLAP` (default 20), `SEGMENT_GAP_MINUTES` (default 30)
- `STATUS.md` v6.0.0, `HANDOFF.md`, `CLAUDE.md`, `AGENT.md`,
  `README.md`, `README_ENV.md` — update architecture, add segment
  pipeline description, update file tree.

---

## Testing Plan

### Phase 1: Schema
1. Restart bot. Verify `schema/008.sql` applied — segments,
   segment_messages, cluster_segments tables exist.
2. Existing tables unmodified.

### Phase 2: Segmentation
3. Run `!summary create` on Channel 2 (project channel, 59 clusters).
4. Check segment count: expect 80–200 segments from ~800 messages.
5. Run `!debug segments` — verify topic labels are descriptive,
   syntheses are self-contained and resolve implicit meaning.
6. Spot-check: find a segment containing a "yes"/"agreed" message.
   Verify the synthesis states what was agreed to.

### Phase 3: Clustering
7. Check cluster count after rebuild — likely fewer, denser clusters
   (clustering 150 segments vs 800 messages).
8. Spot-check cluster labels — should be coherent.
9. Verify `cluster_segments` table populated, `cluster_messages` also
   populated (rollback path).

### Phase 4: Retrieval Benchmark
10. Run `retrieval_benchmark.py --verbose` on Channel 2.
11. Compare against `benchmark_baseline_v5.13.json`.
12. Key metrics to beat:
    - Avg top score > 0.45 (baseline 0.377)
    - Keyword recall > 40% (baseline 19%)
    - Empty retrievals < 5% (baseline 8%)
    - Abstract query scores > 0.40 (baseline ~0.32)
13. If targets not met: check segment quality first (are syntheses
    good?), then embedding quality, then UMAP parameters.

### Phase 5: Citation
14. Ask a question in Discord that triggers retrieval.
15. Verify [N] citations appear in response with Sources footer.
16. Verify `!explain` shows segment-based cluster info.
17. Verify `!explain detail` shows source messages.

### Phase 6: Fallback
18. Test time-gap fallback: temporarily break the Gemini call (e.g.,
    invalid API key) and run `!summary create`. Should fall back to
    gap-based segmentation with concatenated messages.
19. Verify clustering still produces usable results.

### Phase 7: Rollback
20. Set `use_segments=False` in summarizer routing.
21. Run `!summary create` — should use message-based clustering.
22. Verify retrieval works with message-based clusters.

### Phase 8: Regression
23. All existing commands work: `!summary`, `!explain`, `!status`,
    `!debug clusters`, `!ai`, `!prompt`, etc.
24. Bot responds normally to addressed messages.
25. Citations appear with Anthropic provider.

---

## Cost Estimate

For Channel 2 (~800 messages, ~150 segments):

| Step | Calls | Est. Cost |
|------|-------|-----------|
| Segmentation + synthesis | ~2 | ~$0.015 |
| Embed syntheses | 1 batch | <$0.01 |
| Cluster summarization | ~15 | ~$0.01 |
| Classifier + overview | ~5 | <$0.01 |
| **Total** | | **~$0.04** |

Current pipeline: ~$0.01. Increase is from segmentation/synthesis.

---

## Success Criteria

| Metric | Baseline (v5.13) | Target |
|--------|-----------------|--------|
| Avg top score | 0.377 | > 0.45 |
| Keyword recall | 19% | > 40% |
| Empty retrievals | 8% | < 5% |
| Ch2 abstract queries | ~0.32 | > 0.40 |
| Segment quality | N/A | Spot-check: syntheses resolve implicit meaning |

If targets are met, commit. If not, investigate before deciding
whether to iterate or rollback.

---

## Implementation Sequence (for Claude Code)

1. `schema/008.sql` — create tables
2. `utils/segment_store.py` v1.0.0 — CRUD functions
3. `utils/segmenter.py` v1.0.0 — Gemini segmentation + synthesis
4. `utils/cluster_engine.py` v1.1.0 — add `cluster_segments()`
5. `utils/cluster_store.py` v2.1.0 — segment-aware clustering
6. `utils/cluster_summarizer.py` v1.1.0 — segment-aware summaries
7. `utils/cluster_retrieval.py` v1.1.0 — `get_cluster_content()`
8. `utils/context_retrieval.py` v1.5.0 — segment-based context
9. `utils/summarizer.py` v4.1.0 — wire segmentation into pipeline
10. `commands/cluster_commands.py` v1.4.0 — `!debug segments`
11. `config.py` v1.16.0 — new env vars
12. All documentation updates

---

## Constraints

1. Full files only — no partial patches
2. Increment version numbers — v6.0.0 for this release
3. 250-line file limit per file
4. All development on `claude-code` branch
5. Batch mode only — incremental deferred to v6.1.0
6. Retain message_embeddings and cluster_messages for rollback
7. Citations reference individual messages, not segments
8. No artificial segment size limits — let LLM decide
9. Combined segmentation + synthesis in one Gemini call
10. Time-gap fallback if LLM segmentation fails
11. Update all documentation alongside code changes
12. Discuss before coding — get approval before implementing
