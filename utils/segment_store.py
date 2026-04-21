# utils/segment_store.py
# Version 1.1.0
"""
Segment CRUD, query, and clustering for v6.0.0+ pipeline.

CHANGES v1.1.0: Entity status helpers (SOW v7.1.0 M2)
- ADDED: update_segment_status, update_channel_segment_status, get_segment_status_counts
- MODIFIED: run_segment_clustering — set 'clustered'/'unclustered' after clustering
- MOVED: get_cluster_content → cluster_retrieval.py (inlined the delegate wrapper)
CHANGES v1.0.1: updated_at fix in _store_segment_cluster_record
CREATED v1.0.0: Segment CRUD + clustering pipeline (SOW v6.0.0)
"""
import sqlite3
from datetime import datetime, timezone
from config import DATABASE_PATH
from utils.embedding_store import unpack_embedding, pack_embedding
from utils.logging_utils import get_logger

logger = get_logger('segment_store')


def store_segments(channel_id, segments):
    """Bulk insert segments + segment_messages. IDs: seg-{channel_id}-{seq}.

    segments: list of dicts — topic_label, synthesis, message_ids (list),
              first_message_at, last_message_at.
    Returns list of generated segment IDs.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    created_at = datetime.now(timezone.utc).isoformat()
    seg_ids = []
    try:
        for seq, seg in enumerate(segments):
            seg_id = f"seg-{channel_id}-{seq}"
            msg_ids = seg["message_ids"]
            conn.execute(
                "INSERT OR REPLACE INTO segments "
                "(id, channel_id, topic_label, synthesis, message_count, "
                " first_message_id, last_message_id, first_message_at, "
                " last_message_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (seg_id, channel_id, seg.get("topic_label"), seg["synthesis"],
                 len(msg_ids), msg_ids[0], msg_ids[-1],
                 seg.get("first_message_at"), seg.get("last_message_at"),
                 created_at))
            for pos, mid in enumerate(msg_ids):
                conn.execute(
                    "INSERT OR REPLACE INTO segment_messages "
                    "(segment_id, message_id, position) VALUES (?,?,?)",
                    (seg_id, mid, pos))
            seg_ids.append(seg_id)
        conn.commit()
        logger.info(f"Stored {len(seg_ids)} segments for ch:{channel_id}")
        return seg_ids
    finally:
        conn.close()


def clear_channel_segments(channel_id):
    """Delete all segments, segment_messages, cluster_segments for a channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        seg_ids = [r[0] for r in conn.execute(
            "SELECT id FROM segments WHERE channel_id=?",
            (channel_id,)).fetchall()]
        if seg_ids:
            ph = ",".join("?" * len(seg_ids))
            conn.execute(
                f"DELETE FROM cluster_segments WHERE segment_id IN ({ph})",
                seg_ids)
            conn.execute(
                f"DELETE FROM segment_messages WHERE segment_id IN ({ph})",
                seg_ids)
        conn.execute("DELETE FROM segments WHERE channel_id=?", (channel_id,))
        conn.commit()
        logger.info(f"Cleared {len(seg_ids)} segments for ch:{channel_id}")
    finally:
        conn.close()


def get_segment_embeddings(channel_id):
    """Return (segment_id, vector) pairs for all embedded segments in channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id, embedding FROM segments "
            "WHERE channel_id=? AND embedding IS NOT NULL",
            (channel_id,)).fetchall()
        return [(r[0], unpack_embedding(r[1])) for r in rows]
    finally:
        conn.close()


def get_segments_by_ids(segment_ids):
    """Return segment dicts for given IDs. [{"id","topic_label","synthesis"}]."""
    if not segment_ids:
        return []
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        ph = ",".join("?" * len(segment_ids))
        rows = conn.execute(
            f"SELECT id, topic_label, synthesis FROM segments WHERE id IN ({ph})",
            list(segment_ids)).fetchall()
        return [{"id": r[0], "topic_label": r[1], "synthesis": r[2]} for r in rows]
    finally:
        conn.close()


def get_cluster_segment_ids(cluster_id):
    """Return segment IDs for a cluster, ordered by first_message_at ASC."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT cs.segment_id FROM cluster_segments cs JOIN segments s ON s.id=cs.segment_id "
            "WHERE cs.cluster_id=? ORDER BY s.first_message_at ASC", (cluster_id,)).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def store_segment_embedding(segment_id, embedding):
    """Upsert a segment embedding blob."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute("UPDATE segments SET embedding=? WHERE id=?",
                     (pack_embedding(embedding), segment_id))
        conn.commit()
    finally:
        conn.close()


def get_segment_count(channel_id):
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM segments WHERE channel_id=?", (channel_id,)).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def store_cluster_segments(cluster_id, segment_ids):
    """Insert segment_id entries into cluster_segments junction table."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO cluster_segments(cluster_id,segment_id) VALUES(?,?)",
            [(cluster_id, s) for s in segment_ids])
        conn.commit()
    finally:
        conn.close()


def update_segment_status(segment_id, status):
    """Set status on one segment."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute("UPDATE segments SET status=? WHERE id=?", (status, segment_id))
        conn.commit()
    finally:
        conn.close()

def update_channel_segment_status(channel_id, from_status, to_status):
    """Bulk-update segments: from_status → to_status for a channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "UPDATE segments SET status=? WHERE channel_id=? AND status=?",
            (to_status, channel_id, from_status))
        conn.commit()
    finally:
        conn.close()

def get_segment_status_counts(channel_id):
    """Return {status: count} dict for a channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) FROM segments "
            "WHERE channel_id=? GROUP BY status", (channel_id,)).fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        conn.close()


def _clear_channel_cluster_segments(channel_id):
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "DELETE FROM cluster_segments WHERE cluster_id IN "
            "(SELECT id FROM clusters WHERE channel_id=?)", (channel_id,))
        conn.commit()
    finally:
        conn.close()

def _store_segment_cluster_record(channel_id, label, centroid_vec, seq):
    cluster_id = f"seg-cluster-{channel_id}-{seq}"
    created_at = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO clusters"
            "(id,channel_id,label,summary,status,created_at,updated_at,needs_resummarize,embedding)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (cluster_id, channel_id, label, None, "active",
             created_at, created_at, 0, pack_embedding(centroid_vec)))
        conn.commit()
        return cluster_id
    finally:
        conn.close()


def run_segment_clustering(channel_id):
    """UMAP+HDBSCAN on segment embeddings; store cluster records + junction rows.

    Returns stats dict or None if too few segments.
    Writes to clusters + cluster_segments. Does NOT touch cluster_messages.
    """
    from utils.cluster_engine import cluster_segments as _cluster_segs
    from utils.cluster_store import clear_channel_clusters

    result = _cluster_segs(channel_id)
    if result is None:
        return None

    _clear_channel_cluster_segments(channel_id)
    clear_channel_clusters(channel_id)

    for seq, (_, data) in enumerate(result["clusters"].items()):
        centroid = data["centroid"].tolist()
        cluster_id = _store_segment_cluster_record(
            channel_id, f"Cluster {seq}", centroid, seq)
        store_cluster_segments(cluster_id, data["segment_ids"])

    update_channel_segment_status(channel_id, 'indexed', 'unclustered')
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "UPDATE segments SET status='clustered' WHERE channel_id=? AND id IN"
            "(SELECT segment_id FROM cluster_segments cs JOIN clusters c ON c.id=cs.cluster_id"
            " WHERE c.channel_id=?)", (channel_id, channel_id))
        conn.commit()
    finally:
        conn.close()

    stats = result["stats"]
    logger.info(
        f"Segment clustering ch:{channel_id}: "
        f"{stats['cluster_count']} clusters, {stats['noise_count']} noise")
    return stats
