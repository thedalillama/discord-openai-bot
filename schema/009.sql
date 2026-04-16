-- schema/009.sql
-- v6.2.0: FTS5 full-text search for hybrid retrieval
--
-- Creates a virtual FTS5 table over segment syntheses and their source message
-- content. Populated by populate_fts() in utils/fts_search.py during
-- !summary create. Enables BM25 keyword matching to complement dense retrieval.

CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
    segment_id UNINDEXED,
    channel_id UNINDEXED,
    searchable_text,
    tokenize="porter unicode61"
);
