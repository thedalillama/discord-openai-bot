-- schema/003.sql
-- v3.2.1: Add is_bot_author flag to messages table

ALTER TABLE messages ADD COLUMN is_bot_author INTEGER DEFAULT 0;
