-- schema/012.sql
-- v7.1.0: Entity status columns (SOW v7.1.0 M2)

-- Segments: add status column (default 'created')
ALTER TABLE segments ADD COLUMN status TEXT DEFAULT 'created';

-- Index for pipeline status queries
CREATE INDEX IF NOT EXISTS idx_segments_status
  ON segments(channel_id, status);
CREATE INDEX IF NOT EXISTS idx_clusters_status
  ON clusters(channel_id, status);

-- One-time migration: set correct status for existing segments
-- Segments in cluster_segments have been fully processed
UPDATE segments SET status = 'clustered'
  WHERE id IN (SELECT segment_id FROM cluster_segments);

-- Segments with embeddings but not in any cluster are 'unclustered'
UPDATE segments SET status = 'unclustered'
  WHERE status = 'created'
  AND embedding IS NOT NULL
  AND id NOT IN (SELECT segment_id FROM cluster_segments);

-- Any remaining 'created' segments with embeddings only get 'embedded'
UPDATE segments SET status = 'embedded'
  WHERE status = 'created'
  AND embedding IS NOT NULL;
