-- schema/010.sql
-- Version 6.4.0: proposition decomposition table (SOW v6.3.0)
-- Propositions are atomic claims decomposed from segment syntheses by
-- GPT-4o-mini. Each proposition gets its own embedding for query-time
-- scoring. At retrieval, propositions collapse to max-score-per-segment
-- before entering RRF fusion with dense + BM25 signals.
CREATE TABLE IF NOT EXISTS propositions (
    id          TEXT PRIMARY KEY,       -- prop-{segment_id}-{seq}
    segment_id  TEXT NOT NULL,
    channel_id  INTEGER NOT NULL,
    content     TEXT NOT NULL,
    embedding   BLOB,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (segment_id) REFERENCES segments(id)
);
CREATE INDEX IF NOT EXISTS idx_propositions_channel
    ON propositions(channel_id);
CREATE INDEX IF NOT EXISTS idx_propositions_segment
    ON propositions(segment_id);
