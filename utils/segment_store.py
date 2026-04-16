# utils/segment_store.py
# Version 1.0.1
"""
Segment CRUD, query, and segment-based clustering (SOW v6.0.0).

CHANGES v1.0.1: Add updated_at to _store_segment_cluster_record INSERT (was NOT NULL error)
CREATED v1.0.0: Segment pipeline storage (SOW v6.0.0)
- CRUD: store_segments, clear_channel_segments, store_segment_embedding, store_cluster_segments, get_segment_count
- Query: get_segment_embeddings, get_segments_by_ids, get_cluster_segment_ids, get_cluster_content
- Clustering: run_segment_clustering — UMAP+HDBSCAN on segments; writes to clusters + cluster_segments (not cluster_messages)
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
            "SELECT cs.segment_id FROM cluster_segments cs "
            "JOIN segments s ON s.id=cs.segment_id "
            "WHERE cs.cluster_id=? ORDER BY s.first_message_at ASC",
            (cluster_id,)).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def get_cluster_content(cluster_id, exclude_ids=None):
    """Return segment syntheses and source messages for a cluster.

    Returns [{"segment_id", "synthesis", "topic_label",
    "messages": [(msg_id, author, content, created_at), ...]}].
    """
    exclude = set(exclude_ids or [])
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        segs = conn.execute(
            "SELECT s.id, s.topic_label, s.synthesis FROM cluster_segments cs "
            "JOIN segments s ON s.id=cs.segment_id "
            "WHERE cs.cluster_id=? ORDER BY s.first_message_at ASC",
            (cluster_id,)).fetchall()
        result = []
        for seg_id, topic_label, synthesis in segs:
            msgs = conn.execute(
                "SELECT m.id, m.author_name, m.content, m.created_at "
                "FROM segment_messages sm JOIN messages m ON m.id=sm.message_id "
                "WHERE sm.segment_id=? ORDER BY sm.position ASC",
                (seg_id,)).fetchall()
            result.append({
                "segment_id":  seg_id,
                "topic_label": topic_label or "",
                "synthesis":   synthesis,
                "messages":    [(r[0], r[1], r[2], r[3])
                                for r in msgs if r[0] not in exclude],
            })
        return result
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
    """Return count of segments for a channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM segments WHERE channel_id=?",
            (channel_id,)).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def store_cluster_segments(cluster_id, segment_ids):
    """Insert segment_id entries into cluster_segments junction table."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        for seg_id in segment_ids:
            conn.execute(
                "INSERT OR IGNORE INTO cluster_segments "
                "(cluster_id, segment_id) VALUES (?,?)", (cluster_id, seg_id))
        conn.commit()
    finally:
        conn.close()


def _clear_channel_cluster_segments(channel_id):
    """Delete cluster_segments rows for all clusters in this channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "DELETE FROM cluster_segments WHERE cluster_id IN "
            "(SELECT id FROM clusters WHERE channel_id=?)", (channel_id,))
        conn.commit()
    finally:
        conn.close()


def _store_segment_cluster_record(channel_id, label, centroid_vec, seq):
    """Insert cluster row WITHOUT touching cluster_messages (rollback safe).

    Returns cluster_id.
    """
    cluster_id = f"seg-cluster-{channel_id}-{seq}"
    created_at = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO clusters "
            "(id, channel_id, label, summary, status, created_at, updated_at, "
            " needs_resummarize, embedding) VALUES (?,?,?,?,?,?,?,?,?)",
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

    stats = result["stats"]
    logger.info(
        f"Segment clustering ch:{channel_id}: "
        f"{stats['cluster_count']} clusters, {stats['noise_count']} noise")
    return stats
