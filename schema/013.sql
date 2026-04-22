-- schema/013.sql
-- v7.2.0: Reset archived clusters to active (SOW v7.2.0)
-- Gemini was incorrectly setting status='archived'; classifier owns keep/drop.

UPDATE clusters SET status = 'active' WHERE status = 'archived';
