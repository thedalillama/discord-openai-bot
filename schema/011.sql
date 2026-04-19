-- schema/011.sql
-- v7.0.0 M1: Pipeline state tracking (SOW v7.0.0)
--
-- Stores per-channel pipeline progress. last_segmented_message_id is the
-- highest message ID that has been segmented. Used to identify unsummarized
-- messages (id > pointer) for Layer 2 context injection. unsegmented_count
-- is NOT stored — it is always computed from the DB to avoid counter drift.

CREATE TABLE IF NOT EXISTS pipeline_state (
    channel_id                 INTEGER PRIMARY KEY,
    last_segmented_message_id  INTEGER DEFAULT 0,
    last_pipeline_run          TEXT,
    created_at                 TEXT NOT NULL
);
