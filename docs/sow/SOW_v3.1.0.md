# SOW v3.1.0 — Schema Extension & Enhanced Capture (Roadmap M1)

**Status**: Proposed — awaiting approval
**Branch**: development
**Prerequisite**: v3.0.0 merged to main (M0 complete)
**Roadmap reference**: Phase 1, Milestone 1

## Problem Statement

The v3.0.0 persistence layer captures 8 fields per message. The
Summarization Feature Specification (Section 6.1) requires 5 additional
fields for downstream summarization: `reply_to_message_id`, `thread_id`,
`edited_at`, `deleted_at`, and `attachments_metadata`. Without these,
the episode segmenter (M4) cannot group reply chains or thread
boundaries, and the summarizer (M2) cannot distinguish edited or
deleted content from active conversation.

Additionally, the schema definition is currently an inline Python string
(`SCHEMA_SQL`) in `message_store.py`, which is at 249 lines and cannot
absorb further growth. Future milestones will add more tables
(`channel_summaries`, `response_context_receipts`, `episodes`, etc.)
and the current approach does not scale.

## Objectives

1. Extend the `messages` table with 5 new columns for spec compliance.
2. Extract all schema definitions into versioned SQL files with a
   migration runner, so future schema changes require only a new file.
3. Update event handlers to capture the new fields on live messages.
4. Create empty `channel_summaries` and `response_context_receipts`
   tables (populated by M2 and M5 respectively).
5. No backfill of historical messages — new fields populate going
   forward only (event-based fields like `edited_at` and `deleted_at`
   cannot be recovered retroactively).

## Design

### Schema File Architecture

New `schema/` directory at project root containing sequentially numbered
SQL files. Each file is a self-contained migration.

```
schema/
  001.sql    # v3.0.0 baseline — messages, channel_state, indexes
  002.sql    # v3.1.0 — ALTER TABLE additions, new empty tables, schema_version
```

New `schema_version` table tracks which migrations have been applied:

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
```

### Migration Runner (`utils/db_migration.py`)

New module responsible for:

1. Creating `schema_version` table if it doesn't exist
2. Scanning `schema/` directory for `NNN.sql` files
3. Comparing against applied versions in `schema_version`
4. Executing unapplied migrations in sequential order
5. Recording each applied migration with timestamp

Called from `init_database()` in `message_store.py`, replacing the
inline `SCHEMA_SQL` executescript. The runner is idempotent — running
it against an already-current database is a no-op.

For existing v3.0.0 databases, `001.sql` uses `CREATE TABLE IF NOT
EXISTS` so it completes without error. The runner then records version
1 as applied and proceeds to `002.sql`.

### 001.sql — Baseline (v3.0.0)

Extracted verbatim from the current `SCHEMA_SQL` constant in
`message_store.py`:

```sql
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    author_name TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    message_type INTEGER DEFAULT 0,
    is_deleted INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_channel_time
    ON messages(channel_id, created_at);
CREATE INDEX IF NOT EXISTS idx_channel_id
    ON messages(channel_id, id);

CREATE TABLE IF NOT EXISTS channel_state (
    channel_id INTEGER PRIMARY KEY,
    last_processed_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 002.sql — M1 Extensions (v3.1.0)

```sql
-- Extended message fields (Summarization Spec Section 6.1)
ALTER TABLE messages ADD COLUMN reply_to_message_id INTEGER DEFAULT NULL;
ALTER TABLE messages ADD COLUMN thread_id INTEGER DEFAULT NULL;
ALTER TABLE messages ADD COLUMN edited_at TEXT DEFAULT NULL;
ALTER TABLE messages ADD COLUMN deleted_at TEXT DEFAULT NULL;
ALTER TABLE messages ADD COLUMN attachments_metadata TEXT DEFAULT NULL;

-- Index for reply chain grouping (used by episode segmenter, M4)
CREATE INDEX IF NOT EXISTS idx_reply_to
    ON messages(reply_to_message_id)
    WHERE reply_to_message_id IS NOT NULL;

-- Index for thread grouping (used by episode segmenter, M4)
CREATE INDEX IF NOT EXISTS idx_thread
    ON messages(thread_id)
    WHERE thread_id IS NOT NULL;

-- Channel summaries: structured JSON summary per channel (M2)
CREATE TABLE IF NOT EXISTS channel_summaries (
    channel_id INTEGER PRIMARY KEY,
    summary_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    message_count INTEGER DEFAULT 0,
    last_message_id INTEGER DEFAULT NULL
);

-- Response context receipts: exact prompt context per bot response (M5)
CREATE TABLE IF NOT EXISTS response_context_receipts (
    response_message_id INTEGER PRIMARY KEY,
    user_message_id INTEGER,
    channel_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    receipt_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_receipt_channel
    ON response_context_receipts(channel_id, created_at);
```

All ALTER TABLE statements use DEFAULT NULL, so existing rows are
unaffected. SQLite handles ALTER TABLE ADD COLUMN without rebuilding
the table.

### StoredMessage Dataclass Changes

Add 5 optional fields, all defaulting to None:

```python
@dataclass(slots=True)
class StoredMessage:
    id: int
    channel_id: int
    author_id: int
    author_name: str
    content: str
    created_at: str
    message_type: int = 0
    is_deleted: bool = False
    # v3.1.0 additions
    reply_to_message_id: int | None = None
    thread_id: int | None = None
    edited_at: str | None = None
    deleted_at: str | None = None
    attachments_metadata: str | None = None
```

### Event Handler Changes

**`persistence_on_message` (raw_events.py):**

Capture three new fields from the discord.py Message object:

- `reply_to_message_id`: from `message.reference.message_id` if
  `message.reference` is not None
- `thread_id`: from `message.channel.id` if
  `isinstance(message.channel, discord.Thread)`, else None
- `attachments_metadata`: JSON string from `message.attachments` list,
  storing `[{"filename": ..., "size": ..., "content_type": ...}, ...]`
  or None if empty

**`on_raw_message_edit` (raw_events.py):**

Current behavior: updates content only. New behavior: also sets
`edited_at` to the current UTC ISO 8601 timestamp. New function
`update_message_content_and_edit_time()` in `message_store.py`
replaces `update_message_content()`.

**`soft_delete_message` (message_store.py):**

Current behavior: sets `is_deleted = 1`. New behavior: also sets
`deleted_at` to the current UTC ISO 8601 timestamp.

**`_backfill_channel` (raw_events.py):**

Capture `reply_to_message_id`, `thread_id`, and
`attachments_metadata` during backfill (these are available from
the Discord API on historical messages). `edited_at` and `deleted_at`
are not available during backfill.

### message_store.py Changes

- Remove `SCHEMA_SQL` constant (moved to `schema/001.sql`)
- `init_database()` calls `run_migrations(conn)` from `db_migration.py`
  instead of executing inline SQL
- `insert_message()` and `insert_messages_batch()`: add 3 new columns
  to INSERT statements (`reply_to_message_id`, `thread_id`,
  `attachments_metadata`). `edited_at` and `deleted_at` are not set
  on insert (they are set by edit/delete handlers).
- `update_message_content()` replaced by
  `update_message_content_and_edit_time()` which sets both content
  and edited_at
- `soft_delete_message()` updated to set both `is_deleted = 1` and
  `deleted_at` timestamp
- `get_channel_messages()`: updated SELECT and StoredMessage
  construction to include new columns

### Line Count Impact on message_store.py

Current: 249 lines. Changes:

- Remove: ~20 lines (SCHEMA_SQL constant)
- Add: ~15 lines (new columns in INSERT/SELECT, updated edit/delete)
- Net: ~244 lines (within limit)

## New Files

| File | Version | Description |
|------|---------|-------------|
| `utils/db_migration.py` | v1.0.0 | Migration runner: scans schema/, applies new migrations |
| `schema/001.sql` | — | v3.0.0 baseline schema (extracted from message_store.py) |
| `schema/002.sql` | — | v3.1.0 extensions: 5 new columns, 2 new tables |
| `docs/sow/SOW_v3.1.0.md` | — | This document |

## Modified Files

| File | Old Version | New Version | Changes |
|------|------------|-------------|---------|
| `utils/models.py` | v1.0.0 | v1.1.0 | Add 5 optional fields to StoredMessage |
| `utils/message_store.py` | v1.0.0 | v1.1.0 | Remove SCHEMA_SQL, call migration runner, update INSERT/SELECT/UPDATE for new columns |
| `utils/raw_events.py` | v1.0.2 | v1.1.0 | Capture reply_to, thread_id, attachments in on_message and backfill; pass edited_at on edit |
| `STATUS.md` | v3.0.0 | v3.1.0 | Version history |
| `HANDOFF.md` | v3.0.0 | v3.1.0 | Current state |

## Unchanged Files

bot.py, config.py, all providers, all commands, context_manager.py,
response_handler.py, and the entire `utils/history/` subsystem.

## Risk Assessment

**Low.** All schema changes are additive (ALTER TABLE ADD COLUMN with
DEFAULT NULL). No existing data is modified. No existing code paths
change behavior. The migration runner uses CREATE TABLE IF NOT EXISTS
and version tracking, so it is safe to run against both new and
existing databases.

The only behavioral change is that new messages will have additional
fields populated. Existing code that reads StoredMessage will see None
for the new fields on historical rows, which is handled by the default
values in the dataclass.

## Testing

1. **Fresh database**: Delete `data/messages.db`, restart bot. Verify
   both migrations apply, all tables created, schema_version shows
   versions 1 and 2.
2. **Existing database**: Restart bot with existing v3.0.0 database.
   Verify 001.sql is recorded as applied (no-op), 002.sql adds new
   columns and tables. Existing data intact.
3. **Reply capture**: Reply to a message in Discord. Query the database
   and verify `reply_to_message_id` is populated with the referenced
   message ID.
4. **Thread capture**: Post in a thread. Verify `thread_id` is the
   thread's channel ID.
5. **Attachment capture**: Post a message with an attachment. Verify
   `attachments_metadata` contains valid JSON with filename and size.
6. **Edit capture**: Edit a message. Verify content is updated and
   `edited_at` is set to an ISO 8601 timestamp.
7. **Delete capture**: Delete a message. Verify `is_deleted = 1` and
   `deleted_at` is set.
8. **Backfill**: Clear `channel_state` for one channel, restart bot.
   Verify backfilled messages have `reply_to_message_id`, `thread_id`,
   and `attachments_metadata` populated where applicable.
9. **Empty tables**: Verify `channel_summaries` and
   `response_context_receipts` tables exist and are empty.
10. **Stats**: Run `get_database_stats()` — verify no errors.
