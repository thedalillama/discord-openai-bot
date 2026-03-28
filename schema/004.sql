-- schema/004.sql
-- v4.0.0: Topic-based semantic retrieval tables

-- Topics as first-class entities with embeddings
CREATE TABLE IF NOT EXISTS topics (
    id         TEXT    PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    title      TEXT    NOT NULL,
    summary    TEXT,
    status     TEXT    DEFAULT 'active',
    embedding  BLOB,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_topics_channel
    ON topics(channel_id, status);

-- Junction: which messages belong to which topic (by embedding similarity)
CREATE TABLE IF NOT EXISTS topic_messages (
    topic_id   TEXT    NOT NULL,
    message_id INTEGER NOT NULL,
    PRIMARY KEY (topic_id, message_id),
    FOREIGN KEY (topic_id)   REFERENCES topics(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);
CREATE INDEX IF NOT EXISTS idx_topic_messages_message
    ON topic_messages(message_id);

-- Message embeddings (computed once on arrival, cached forever)
CREATE TABLE IF NOT EXISTS message_embeddings (
    message_id INTEGER PRIMARY KEY,
    embedding  BLOB    NOT NULL,
    FOREIGN KEY (message_id) REFERENCES messages(id)
);
