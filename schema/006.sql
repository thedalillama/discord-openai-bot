-- schema/006.sql
-- v5.4.0: Incremental cluster assignment support

ALTER TABLE clusters ADD COLUMN needs_resummarize INTEGER DEFAULT 0;
