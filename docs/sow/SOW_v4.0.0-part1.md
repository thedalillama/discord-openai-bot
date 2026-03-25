# SOW v4.0.0 — Episode Segmentation (Roadmap M4)
# Part 1 of 2: Problem, Design, and Data Model

**Status**: Proposed — awaiting approval
**Branch**: claude-code
**Prerequisite**: v3.5.2 (overview inflation fix complete)
**Roadmap reference**: Phase 4, Milestone 4

---

## Problem Statement

The current summary is a single flat document that grows indefinitely with
channel activity. After 500+ messages, the summary is already at 2,097
tokens. Dedup and the Classifier control growth, but the fundamental model
has no concept of time. A decision made 6 months ago sits alongside one
made today with equal weight.

Three failure modes emerge as channels mature:

**1. Token ceiling.** The 16,384 token budget is eventually consumed by
legitimate history. The Secretary must then truncate or compress to fit,
losing fidelity on recent content.

**2. Staleness without signal.** Topics and decisions marked "active" may
refer to work completed months ago. The summary has no mechanism to detect
stale items — only that they were once active.

**3. Context dilution.** M3 injects the full summary into every conversation
context. As the summary grows, it increasingly loads the context window with
history irrelevant to the current exchange.

Episode segmentation solves all three by dividing the channel's history into
discrete, sealed sessions. Each episode has a coherent start and end. The
live summary stays bounded. Old episodes are archived but queryable.

---

## What is an Episode?

An episode is a bounded window of conversation activity with a detectable
start and end.

**Episode boundary**: a time gap of ≥ `EPISODE_GAP_HOURS` between the
last summarized message and the first new message in an incremental run.
Default threshold: 4 hours. Configurable via `.env`.

This is intentionally simple. Time gaps are directly observable from message
timestamps. A 4-hour silence in a text channel reliably signals end-of-session
without requiring semantic analysis.

**Episode lifecycle**:
1. **Active** — the current `channel_summaries` row. Accumulates messages
   incrementally (current behavior).
2. **Sealed** — episode ended. Summary snapshot saved to `channel_episodes`.
   `channel_summaries` row is reset to empty for the new episode.
3. **Archived** — sealed episodes older than a configurable window. Not
   loaded into M3 context by default; accessible via `!summary episodes`.

---

## Data Model

### New table: `channel_episodes`

New migration `schema/004.sql`:

```sql
CREATE TABLE IF NOT EXISTS channel_episodes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id   TEXT    NOT NULL,
    episode_num  INTEGER NOT NULL,
    started_at   TEXT    NOT NULL,
    ended_at     TEXT    NOT NULL,
    summary_json TEXT    NOT NULL,
    token_count  INTEGER DEFAULT 0,
    created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_episodes_channel
    ON channel_episodes(channel_id, episode_num);
```

### Modified: `channel_summaries`

```sql
ALTER TABLE channel_summaries ADD COLUMN episode_num INTEGER DEFAULT 1;
```

The `channel_summaries` row now represents the **current episode only**. When
sealed, the row resets to an empty summary and `episode_num` increments.

### Summary JSON: new `meta.episode` fields

The sealed summary JSON gets two new fields under `meta`:

```json
"meta": {
  "episode_num": 3,
  "episode_started_at": "2026-03-01T14:00:00Z",
  "episode_ended_at":   "2026-03-01T22:45:00Z",
  ...
}
```

These are written at seal time and never modified.

---

## Episode Detection Algorithm

Runs at the top of `incremental_pipeline()`, before the Secretary call:

```
1. Fetch timestamp of last summarized message:
       last_ts = lookup(msgs table, current.meta.message_range.last_id)
   If no prior summary exists: skip detection (cold start path).

2. Fetch timestamp of first new message:
       first_new_ts = msgs[0].created_at

3. gap_hours = (first_new_ts - last_ts).total_seconds() / 3600

4. If gap_hours >= EPISODE_GAP_HOURS:
       a. Write current summary to channel_episodes (seal)
       b. Reset channel_summaries to make_empty_summary(channel_id)
       c. Set episode_num = old_episode_num + 1
       d. Log: "Episode {N} sealed ({token_count} tokens, {gap:.1f}h gap)"
       e. Run cold_start_pipeline(msgs) instead of incremental

5. Else: proceed with incremental_pipeline() as normal.
```

Sealing is a single SQL insert + update. `cold_start_pipeline()` already
handles the fresh-start case (no prior minutes, no existing summary).

---

## Configuration

```python
# config.py addition
EPISODE_GAP_HOURS = float(os.getenv("EPISODE_GAP_HOURS", "4"))
```

---

## New Files

| File | Version | Description |
|------|---------|-------------|
| `schema/004.sql` | — | `channel_episodes` + `episode_num` column migration |
| `utils/episode_store.py` | v1.0.0 | `seal_episode()`, `get_episodes()`, `get_recent_episodes()` |
| `docs/sow/SOW_v4.0.0-part1.md` | — | This document |
| `docs/sow/SOW_v4.0.0-part2.md` | — | Pipeline + context + display + impl plan |

## Modified Files

| File | Old | New | Change |
|------|-----|-----|--------|
| `utils/summarizer_authoring.py` | v1.9.0 | v2.0.0 | Episode detection in `incremental_pipeline()` |
| `utils/summary_store.py` | v1.1.0 | v1.2.0 | `reset_for_new_episode()` |
| `config.py` | v1.11.0 | v1.12.0 | `EPISODE_GAP_HOURS` |

## Unchanged

`apply_ops()`, `summary_schema.py`, `summary_classifier.py`,
`summary_delta_schema.py`, all command modules, all providers, `bot.py`.
Display changes are in Part 2.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Gap threshold seals too aggressively | Medium | Medium | 4h default is conservative; `.env` override available |
| Seal during multi-batch loop | Low | High | Detection runs once before first batch only |
| Cold start on first backfill triggers false episode | Medium | Medium | Detection skipped when `meta.message_range.last_id` is 0 |
| episode_num drift after manual DB reset | Low | Low | Both tables cleared together; `!summary clear` resets to episode 1 |

*Continued in Part 2: Pipeline changes, context injection, display,
and implementation plan.*
