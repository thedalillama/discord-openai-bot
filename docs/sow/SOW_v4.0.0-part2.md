# SOW v4.0.0 — Episode Segmentation (Roadmap M4)
# Part 2 of 2: Pipeline, Context Injection, Display, and Implementation Plan

**Status**: Proposed — awaiting approval
**See also**: SOW_v4.0.0-part1.md for problem, design, and data model.

---

## Pipeline Changes

### `utils/episode_store.py` (new, v1.0.0)

Single-responsibility module for episode persistence:

```python
def seal_episode(channel_id, episode_num, summary, token_count):
    """Save current summary as a sealed episode. Thread-safe (WAL mode)."""

def get_episodes(channel_id, limit=None):
    """Return list of sealed episodes for channel, newest first."""

def get_recent_episodes(channel_id, n=3):
    """Return the N most recent sealed episode summaries."""
```

All functions run synchronously (called via `asyncio.to_thread()`).

### `utils/summarizer_authoring.py` v2.0.0

Changes to `incremental_pipeline()`:

```python
async def incremental_pipeline(channel_id, provider, prov_name,
                                model, msgs, current):
    # NEW: Episode detection block
    gap = _compute_gap_hours(current, msgs)
    if gap is not None and gap >= EPISODE_GAP_HOURS:
        logger.info(f"Episode gap {gap:.1f}h >= {EPISODE_GAP_HOURS}h — "
                    f"sealing episode {current['meta'].get('episode_num', 1)}")
        await asyncio.to_thread(
            seal_episode, channel_id,
            current["meta"].get("episode_num", 1),
            current, current.get("summary_token_count", 0))
        await asyncio.to_thread(reset_for_new_episode, channel_id)
        # Run cold start on new messages instead of incremental
        return await cold_start_pipeline(
            channel_id, provider, len(msgs),
            prov_name, model, msgs)
    # ... existing incremental logic unchanged
```

New helper (private):

```python
def _compute_gap_hours(current, msgs):
    """Return hours between last summarized message and first new message.
    Returns None if gap cannot be determined (first run)."""
    last_id = current.get("meta", {}).get("message_range", {}).get("last_id")
    if not last_id or not msgs:
        return None
    last_ts = _lookup_message_timestamp(last_id)
    if not last_ts:
        return None
    first_new_ts = msgs[0].created_at
    if not first_new_ts:
        return None
    delta = _parse_ts(first_new_ts) - _parse_ts(last_ts)
    return delta.total_seconds() / 3600
```

`_lookup_message_timestamp()` queries the messages table via
`get_channel_messages()` filtered to the specific ID. This is a cheap
point lookup using the existing SQLite store.

### `utils/summary_store.py` v1.2.0

New function:

```python
def reset_for_new_episode(channel_id):
    """Replace channel_summaries row with empty summary, episode_num += 1.
    Called synchronously from asyncio.to_thread()."""
    old_num = get_episode_num(channel_id)  # SELECT episode_num
    empty = make_empty_summary(channel_id)
    empty["meta"]["episode_num"] = old_num + 1
    save_channel_summary(channel_id, json.dumps(empty), last_message_id=None)
    # UPDATE episode_num = old_num + 1 WHERE channel_id = ?
```

---

## M3 Context Injection Changes

### Current behavior (`context_manager.py` v1.1.0)

Injects the full current summary as a block in the system prompt:

```
[Channel Summary]
Overview: ...
Decisions: ...
Topics: ...
```

### New behavior (v1.2.0)

Inject current summary + episode index for recent sealed episodes:

```
[Current Session Summary]
Overview: ...
Decisions: ...
Topics: ...

[Prior Sessions — last 2]
Episode 3 (2026-03-20): Database infrastructure settled on PostgreSQL/GCP.
  Rate limiting at 5000 ipm. README update pending.
Episode 2 (2026-03-15): Bachelor party toast brainstorming. AI model
  pricing discussion. Animal evolution Q&A.
```

Episode index lines are generated from `episode.meta.episode_ended_at` +
`episode.overview`. One line per episode. The current summary is shown in
full as before.

**Context budget**: Current summary unchanged. Episode index limited to
`EPISODE_CONTEXT_LINES = 2` (configurable). Each episode index line is
~20-30 tokens — negligible overhead.

New config:

```python
EPISODE_CONTEXT_COUNT = int(os.getenv("EPISODE_CONTEXT_COUNT", "2"))
```

---

## Display Changes

### `!summary episodes` (new subcommand)

Lists all sealed episodes for the channel:

```
📚 Episode History — #openclaw (3 episodes)

Episode 1 — 2026-03-01 to 2026-03-10 (1,085 tokens)
  Database hosting: PostgreSQL on GCP Cloud SQL us-east1.
  AI model pricing discussion. Animal evolution Q&A.

Episode 2 — 2026-03-15 to 2026-03-18 (743 tokens)
  Bachelor party toasts. Rate limiting at 1000 ipm.

[Current] Episode 3 — 2026-03-20 to present (2,097 tokens)
  Rate limiting updated to 5000 ipm. README update pending.
```

Implementation: `build_episode_list()` in `summary_display.py` v1.3.0.
New command handler in `summary_commands.py` v2.3.0.

### `!summary` (existing)

Unchanged. Shows current episode only. Episode number shown in footer:

```
📋 Summary for #openclaw  [Episode 3]
...
```

Small addition: `summary_display.py` reads `meta.episode_num` and appends
`[Episode N]` to the channel header if `episode_num > 1`.

---

## Implementation Plan

### Step 1 — Schema migration

- Write `schema/004.sql` (table + column)
- `db_migration.py` applies it automatically on next bot start
- No data loss: existing `channel_summaries` rows get `episode_num = 1`

### Step 2 — `episode_store.py`

- Write v1.0.0: `seal_episode()`, `get_episodes()`, `get_recent_episodes()`
- Add `reset_for_new_episode()` to `summary_store.py` v1.2.0
- Unit-test with SQLite in-memory

### Step 3 — Pipeline integration

- Modify `summarizer_authoring.py` v2.0.0
- Modify `config.py` v1.12.0 (`EPISODE_GAP_HOURS`, `EPISODE_CONTEXT_COUNT`)
- Test: create a summary, manually trigger a 4h+ gap, run `!summary create`
- Verify: old episode in `channel_episodes`, new fresh summary started

### Step 4 — Context injection

- Modify `context_manager.py` v1.2.0
- Test: confirm prior episode overview appears in system prompt context

### Step 5 — Display

- Modify `summary_display.py` v1.3.0 (`[Episode N]` footer)
- Modify `summary_commands.py` v2.3.0 (`!summary episodes` handler)
- Test: `!summary episodes` lists all sealed episodes correctly

### Step 6 — Docs + commit

- Update `STATUS.md`, `HANDOFF.md`
- SOWs already written (this doc)

---

## Testing Protocol

```
1. !summary clear
2. !summary create              → Episode 1, cold start
3. Send 3 test messages
4. !summary create              → Episode 1, incremental
5. Wait or manually insert timestamp gap in messages DB
6. Send 3 more test messages
7. !summary create              → Episode 1 seals, Episode 2 cold starts
8. !summary episodes            → shows Episode 1 (sealed) + Episode 2 (current)
9. !summary                     → shows Episode 2 only, footer: [Episode 2]
10. Verify context: send a message, check bot's system prompt includes
    Episode 1 overview line
```

---

## Future Work (M5+)

- `!summary episodes N` — show full detail of episode N
- `!summary search <query>` — search across all episodes (M6 citation)
- Epoch compression (M7): merge oldest episodes into a single summary
  when episode count exceeds threshold
- Episode-aware Classifier: protect items that are "new this episode"
  more aggressively than items carried forward from prior episodes
