-- schema/001.sql
-- v3.0.0 baseline schema (extracted from message_store.py SCHEMA_SQL)

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
