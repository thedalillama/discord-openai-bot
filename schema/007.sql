-- schema/007.sql
-- v5.11.0: Drop dead topic tables
-- topics and topic_messages were part of the v4.x topic-based retrieval
-- system, replaced by cluster-based retrieval in v5.5.0. No code reads
-- or writes these tables since v5.10.0 removed the last references.
-- Data is preserved in git history and old database backups.

DROP TABLE IF EXISTS topic_messages;
DROP TABLE IF EXISTS topics;
