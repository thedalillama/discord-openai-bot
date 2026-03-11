-- schema/002.sql
-- v3.1.0 extensions: 5 new message columns, 2 new tables
-- (Summarization Spec Section 6.1)

-- Extended message fields
ALTER TABLE messages ADD COLUMN reply_to_message_id INTEGER DEFAULT NULL;
ALTER TABLE messages ADD COLUMN thread_id INTEGER DEFAULT NULL;
ALTER TABLE messages ADD COLUMN edited_at TEXT DEFAULT NULL;
ALTER TABLE messages ADD COLUMN deleted_at TEXT DEFAULT NULL;
ALTER TABLE messages ADD COLUMN attachments_metadata TEXT DEFAULT NULL;

-- Index for reply chain grouping (used by episode segmenter)
CREATE INDEX IF NOT EXISTS idx_reply_to
    ON messages(reply_to_message_id)
    WHERE reply_to_message_id IS NOT NULL;

-- Index for thread grouping (used by episode segmenter)
CREATE INDEX IF NOT EXISTS idx_thread
    ON messages(thread_id)
    WHERE thread_id IS NOT NULL;

-- Channel summaries: structured JSON summary per channel
CREATE TABLE IF NOT EXISTS channel_summaries (
    channel_id INTEGER PRIMARY KEY,
    summary_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    message_count INTEGER DEFAULT 0,
    last_message_id INTEGER DEFAULT NULL
);

-- Response context receipts: exact prompt context per bot response
CREATE TABLE IF NOT EXISTS response_context_receipts (
    response_message_id INTEGER PRIMARY KEY,
    user_message_id INTEGER,
    channel_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    receipt_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_receipt_channel
    ON response_context_receipts(channel_id, created_at);
