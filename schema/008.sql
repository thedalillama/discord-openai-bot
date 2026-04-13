-- schema/008.sql
-- v6.0.0: Conversation segmentation tables

CREATE TABLE IF NOT EXISTS segments (
    id               TEXT PRIMARY KEY,
    channel_id       INTEGER NOT NULL,
    topic_label      TEXT,
    synthesis        TEXT NOT NULL,
    embedding        BLOB,
    message_count    INTEGER NOT NULL,
    first_message_id INTEGER NOT NULL,
    last_message_id  INTEGER NOT NULL,
    first_message_at TEXT,
    last_message_at  TEXT,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_segments_channel
    ON segments(channel_id);

CREATE TABLE IF NOT EXISTS segment_messages (
    segment_id TEXT    NOT NULL,
    message_id INTEGER NOT NULL,
    position   INTEGER NOT NULL,
    PRIMARY KEY (segment_id, message_id),
    FOREIGN KEY (segment_id) REFERENCES segments(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);
CREATE INDEX IF NOT EXISTS idx_segment_messages_message
    ON segment_messages(message_id);

CREATE TABLE IF NOT EXISTS cluster_segments (
    cluster_id TEXT NOT NULL,
    segment_id TEXT NOT NULL,
    PRIMARY KEY (cluster_id, segment_id),
    FOREIGN KEY (cluster_id) REFERENCES clusters(id),
    FOREIGN KEY (segment_id) REFERENCES segments(id)
);
