# SOW v3.0.0 — SQLite Message Persistence Layer

**Status**: ✅ Completed
**Branch**: development
**Prerequisite**: development and main in sync at v2.23.0

## Problem Statement

The bot stores conversation history exclusively in memory. On restart,
all messages must be refetched from Discord's API (~8 minutes for 100
channels). The planned summarization subsystem (v3.1.0+) requires access
to complete raw message history (25,000+ messages) for fresh-from-source
summarization via Gemini 2.5 Flash Lite's 1M-token context window. This
eliminates recursive summary drift (14% semantic loss per cycle) but
requires durable local storage that survives restarts.

Research determined SQLite is decisively superior to Discord threads
(the v2.24.0 design): crash-proof, instant restart, queryable, and
keeps RAM under 250 MB versus 2–3 GB for in-memory storage at scale.

## Objective

Add a SQLite persistence layer that captures every message in real-time,
survives restarts, and provides the foundation for summarization in v3.1.0.
**This release adds storage only — no summarization, no Gemini.**

## Why Major Version

New infrastructure dependency (database file on disk), new data lifecycle
(messages persist beyond process lifetime), new Gateway event handlers
(`on_raw_message_*`), and changed startup behavior (backfill vs full
reload). Subsequent features (summarization, epochs) depend on this.

## Design

### SQLite Database

Single file at configurable `DATABASE_PATH` (default `./data/messages.db`).
WAL mode enabled for concurrent read/write safety.

```sql
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,          -- Discord snowflake ID
    channel_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    author_name TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,         -- ISO 8601
    message_type INTEGER DEFAULT 0,
    is_deleted INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_channel_time ON messages(channel_id, created_at);
CREATE INDEX IF NOT EXISTS idx_channel_id ON messages(channel_id, id);

CREATE TABLE IF NOT EXISTS channel_state (
    channel_id INTEGER PRIMARY KEY,
    last_processed_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
```

~160 bytes/row. 2.5M messages (100 channels × 25K) ≈ 400–600 MB on disk.
WAL mode: 30K–80K inserts/sec batched; 25K row query in 50–200 ms on SSD.

### StoredMessage Data Model

Lightweight dataclass (~350 bytes vs ~1,200 for discord.py Message):

```python
@dataclass
class StoredMessage:
    id: int               # Discord snowflake
    channel_id: int
    author_id: int        # Permanent user ID
    author_name: str      # Display name at time of message
    content: str
    created_at: str       # ISO 8601
    message_type: int
    is_deleted: bool
```

### Event Handlers

Message create uses an `on_message` listener registered via
`bot.add_listener()` — not `on_raw_message_create`, which does not
dispatch when `commands.Bot` has a `@bot.event on_message` defined.
Edit and delete use raw listeners (no conflict with cached handlers):

- **on_message listener**: Insert into `messages`, update `last_processed_id`
- **on_raw_message_edit**: UPDATE content if payload contains new content
- **on_raw_message_delete**: SET `is_deleted = 1` (soft delete, never hard-delete)

Bot's own messages ARE stored (needed for summarization context).
These handlers are **independent** of `on_message` in bot.py — the
existing response pipeline is completely unchanged.

### Startup Backfill

In `on_ready()`, after existing initialization:

1. For each visible text channel, query `last_processed_id`
2. Fetch messages from Discord API newer than that ID
3. First run: fetch up to 10,000 recent messages per channel
4. `asyncio.Semaphore(3)` limits concurrent fetches (rate limit safety)
5. Cap at 10,000 messages per channel; log warning if gap is larger

### 250-Line Constraint

bot.py is ~175 lines. Adding handlers + backfill would exceed 250.
**Solution (Option A):** Extracted to `utils/raw_events.py`. bot.py calls
`setup_raw_events(bot)` and `startup_backfill(bot)`. Clean separation
of response pipeline (bot.py) from persistence pipeline (raw_events.py).

## New Files

| File | Lines | Version | Description |
|------|-------|---------|-------------|
| `utils/models.py` | 41 | v1.0.0 | StoredMessage dataclass |
| `utils/message_store.py` | 249 | v1.0.0 | SQLite init, insert, update, soft-delete, query |
| `utils/raw_events.py` | 222 | v1.0.2 | on_message listener, raw edit/delete, backfill |

## Modified Files

| File | Old Version | New Version | Changes |
|------|------------|-------------|---------|
| `bot.py` | v2.10.0 | v3.0.0 | Import raw_events; call setup + backfill |
| `config.py` | v1.6.0 | v1.7.0 | Add DATABASE_PATH env var |
| `.gitignore` | — | — | Add `data/` |

## Unchanged Files

All providers, commands, context_manager.py, response_handler.py,
message_processing.py, and the entire `utils/history/` subsystem.
The in-memory `channel_history` response path is untouched.

## Documentation Updates

| File | Changes |
|------|---------|
| `STATUS.md` | v3.0.0 section; updated file structure |
| `HANDOFF.md` | Rewrite with new architecture and v3.x roadmap |
| `README.md` | Message Persistence section; updated architecture tree |
| `README_ENV.md` | DATABASE_PATH variable; database troubleshooting |
| `docs/sow/SOW_v3.0.0.md` | This document |

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_PATH` | Path to SQLite database file | `./data/messages.db` |

`data/` directory created automatically on first run.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| SQLite write blocks event loop | Medium | High | All writes via `asyncio.to_thread()` |
| Startup backfill hits rate limits | Low | Medium | Semaphore(3); backoff on 429s |
| Database corruption on crash | Very Low | High | WAL mode (ACID-compliant) |
| Disk space growth | Low | Low | ~500 MB for 2.5M messages |
| bot.py exceeds 250 lines | High | Low | Option A: extract to raw_events.py |

## Dependencies

**sqlite3** — Python standard library. No new pip packages.

## Testing

**Phase 1 — Database creation:** ✅
1. Start bot → `data/messages.db` created
2. Schema verified: messages + channel_state tables, 3 indexes
3. WAL mode confirmed

**Phase 2 — Real-time capture:** ✅
4. Messages captured in real-time (3,200+ across 12 channels)
5. Edits update content correctly
6. Deletes set `is_deleted = 1`
7. `channel_state.last_processed_id` advances

**Phase 3 — Restart recovery:** ✅
8. Backfill fetched missed messages (4 on second restart)
9. No duplicate rows (INSERT OR IGNORE)
10. `last_processed_id` correct after backfill

**Phase 4 — Existing behavior unchanged:** ✅
11. Bot responds normally (on_message pipeline intact)
12. All commands work
13. Auto-respond, token-budget context building unchanged

## Bug Fixes During Development

- **v1.0.0 → v1.0.1**: `@bot.event` does not register raw event handlers
  from external modules. Changed to `bot.add_listener()`.
- **v1.0.1 → v1.0.2**: `on_raw_message_create` not dispatched by
  `commands.Bot` when `@bot.event on_message` is defined. Replaced with
  a second `on_message` listener via `bot.add_listener(fn, 'on_message')`.
