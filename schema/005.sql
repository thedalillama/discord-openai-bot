-- schema/005.sql
-- v5.0.0-phase1: Cluster-based summarization tables

CREATE TABLE IF NOT EXISTS clusters (
    id               TEXT    PRIMARY KEY,
    channel_id       INTEGER NOT NULL,
    label            TEXT    NOT NULL DEFAULT '',
    summary          TEXT    NOT NULL DEFAULT '',
    status           TEXT    NOT NULL DEFAULT 'active',
    embedding        BLOB,
    message_count    INTEGER DEFAULT 0,
    first_message_at TEXT,
    last_message_at  TEXT,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cluster_channel
    ON clusters(channel_id);

CREATE TABLE IF NOT EXISTS cluster_messages (
    cluster_id TEXT    NOT NULL,
    message_id INTEGER NOT NULL,
    PRIMARY KEY (cluster_id, message_id),
    FOREIGN KEY (cluster_id)  REFERENCES clusters(id),
    FOREIGN KEY (message_id)  REFERENCES messages(id)
);
