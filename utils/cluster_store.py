# utils/cluster_store.py
# Version 2.0.0
"""
SQLite CRUD and orchestration for cluster-based summarization.

CHANGES v2.0.0: Incremental assignment helpers (SOW v5.4.0)
- ADDED: get_dirty_clusters() — clusters with needs_resummarize=1
- ADDED: mark_clusters_clean() — clear needs_resummarize flag
- ADDED: get_unassigned_message_count() — embedded msgs not in any cluster

CHANGES v1.1.0: get_cluster_message_ids, get_clusters_for_channel,
  update_cluster_label_summary, get_messages_by_ids
CREATED v1.0.0: store_cluster, clear_channel_clusters, get_cluster_stats,
  run_clustering, format_cluster_report (SOW v5.1.0)
"""
import sqlite3
from datetime import datetime, timezone
from config import DATABASE_PATH
from utils.embedding_store import pack_embedding
from utils.logging_utils import get_logger

logger = get_logger('cluster_store')


def store_cluster(channel_id, cluster_label, centroid, message_ids,
                  first_at, last_at):
    """Store a cluster with its centroid embedding and message membership."""
    cluster_id = f"cluster-{channel_id}-{cluster_label}"
    now = datetime.now(timezone.utc).isoformat()
    embedding_blob = pack_embedding(centroid.tolist())
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "INSERT INTO clusters"
            "(id, channel_id, label, summary, status, embedding,"
            " message_count, first_message_at, last_message_at,"
            " created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "embedding=excluded.embedding,"
            "message_count=excluded.message_count,"
            "first_message_at=excluded.first_message_at,"
            "last_message_at=excluded.last_message_at,"
            "updated_at=excluded.updated_at",
            (cluster_id, channel_id, '', '', 'active', embedding_blob,
             len(message_ids), first_at, last_at, now, now))
        conn.execute(
            "DELETE FROM cluster_messages WHERE cluster_id=?", (cluster_id,))
        conn.executemany(
            "INSERT OR IGNORE INTO cluster_messages(cluster_id, message_id)"
            " VALUES (?,?)",
            [(cluster_id, mid) for mid in message_ids])
        conn.commit()
    finally:
        conn.close()


def clear_channel_clusters(channel_id):
    """Delete all clusters and cluster_messages for a channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "DELETE FROM cluster_messages WHERE cluster_id IN "
            "(SELECT id FROM clusters WHERE channel_id=?)", (channel_id,))
        conn.execute(
            "DELETE FROM clusters WHERE channel_id=?", (channel_id,))
        conn.commit()
        logger.debug(f"Cleared clusters for ch:{channel_id}")
    finally:
        conn.close()


def get_cluster_stats(channel_id):
    """Return cluster list and summary counts for !debug clusters."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id, label, message_count, first_message_at,"
            " last_message_at, status "
            "FROM clusters WHERE channel_id=? ORDER BY message_count DESC",
            (channel_id,)).fetchall()
        return [{"cluster_id": r[0], "label": r[1], "message_count": r[2],
                 "first_message_at": r[3], "last_message_at": r[4],
                 "status": r[5]}
                for r in rows]
    finally:
        conn.close()


def run_clustering(channel_id, min_cluster_size=None, min_samples=None):
    """Orchestrate: cluster → clear old → store new. Returns stats or None."""
    from utils.cluster_engine import cluster_messages
    from utils.message_store import get_channel_messages

    result = cluster_messages(channel_id, min_cluster_size, min_samples)
    if result is None:
        return None

    all_msgs = get_channel_messages(channel_id)
    ts_map = {m.id: m.created_at for m in all_msgs if hasattr(m, 'created_at')}

    clear_channel_clusters(channel_id)
    for label, data in result["clusters"].items():
        mids = data["message_ids"]
        timestamps = [ts_map.get(mid) for mid in mids if ts_map.get(mid)]
        first_at = min(timestamps) if timestamps else None
        last_at  = max(timestamps) if timestamps else None
        store_cluster(channel_id, label, data["centroid"],
                      mids, first_at, last_at)

    logger.info(
        f"Stored {result['stats']['cluster_count']} clusters ch:{channel_id}")
    return result["stats"]


def get_cluster_message_ids(cluster_id):
    """Return list of message_ids for a cluster, ordered by created_at."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT cm.message_id FROM cluster_messages cm "
            "JOIN messages m ON m.id=cm.message_id "
            "WHERE cm.cluster_id=? ORDER BY m.created_at ASC",
            (cluster_id,)).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def get_clusters_for_channel(channel_id):
    """Return list of cluster dicts ordered by message_count desc."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id, label, summary, status, message_count,"
            " first_message_at, last_message_at "
            "FROM clusters WHERE channel_id=? ORDER BY message_count DESC",
            (channel_id,)).fetchall()
        return [{"id": r[0], "label": r[1], "summary": r[2], "status": r[3],
                 "message_count": r[4], "first_message_at": r[5],
                 "last_message_at": r[6]}
                for r in rows]
    finally:
        conn.close()


def update_cluster_label_summary(cluster_id, label, summary_json, status):
    """Store LLM-generated label, summary JSON blob, and status."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "UPDATE clusters SET label=?, summary=?, status=?, updated_at=? "
            "WHERE id=?",
            (label, summary_json, status, now, cluster_id))
        conn.commit()
    finally:
        conn.close()


def get_messages_by_ids(message_ids):
    """Return (id, author_name, content, created_at) for given IDs, asc."""
    if not message_ids:
        return []
    placeholders = ",".join("?" * len(message_ids))
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            f"SELECT id, author_name, content, created_at FROM messages "
            f"WHERE id IN ({placeholders}) ORDER BY created_at ASC",
            message_ids).fetchall()
        return [(r[0], r[1], r[2], r[3]) for r in rows]
    finally:
        conn.close()


def get_dirty_clusters(channel_id):
    """Return cluster dicts where needs_resummarize=1 for the channel."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id, label, summary, status, message_count,"
            " first_message_at, last_message_at "
            "FROM clusters WHERE channel_id=? AND needs_resummarize=1"
            " ORDER BY message_count DESC",
            (channel_id,)).fetchall()
        return [{"id": r[0], "label": r[1], "summary": r[2], "status": r[3],
                 "message_count": r[4], "first_message_at": r[5],
                 "last_message_at": r[6]}
                for r in rows]
    finally:
        conn.close()


def mark_clusters_clean(cluster_ids):
    """Set needs_resummarize=0 for the given cluster IDs."""
    if not cluster_ids:
        return
    placeholders = ",".join("?" * len(cluster_ids))
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            f"UPDATE clusters SET needs_resummarize=0"
            f" WHERE id IN ({placeholders})",
            cluster_ids)
        conn.commit()
    finally:
        conn.close()


def get_unassigned_message_count(channel_id):
    """Count embedded messages for channel not assigned to any cluster."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM message_embeddings me "
            "JOIN messages m ON m.id=me.message_id "
            "WHERE m.channel_id=? AND me.message_id NOT IN ("
            " SELECT cm.message_id FROM cluster_messages cm"
            " JOIN clusters c ON c.id=cm.cluster_id"
            " WHERE c.channel_id=?)",
            (channel_id, channel_id)).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def format_cluster_report(channel_name, stats, cluster_rows, params):
    """Format !debug clusters output for Discord."""
    total = stats["total_messages"]
    count = stats["cluster_count"]
    noise = stats["noise_count"]
    pct = stats["noise_ratio"] * 100
    lines = [
        f"ℹ️ **Cluster Analysis** (channel: #{channel_name})",
        f"Messages: {total} total, {count} clusters, {noise} noise ({pct:.1f}%)",
        f"Largest cluster: {stats['largest_cluster_size']} msgs"
        f" ({stats['largest_cluster_fraction']*100:.1f}%)", "",
    ]
    for i, row in enumerate(cluster_rows):
        first = (row["first_message_at"] or "")[:10]
        last  = (row["last_message_at"]  or "")[:10]
        date_range = f"{first} – {last}" if first else "no dates"
        lines.append(f"Cluster {i}: {row['message_count']} msgs ({date_range})")
    lines.append(f"Noise: {noise} msgs unassigned")
    lines.append("")
    lines.append(
        f"Parameters: min_cluster_size={params['mcs']}, min_samples={params['ms']},"
        f" umap_n={params['umap_n']}, umap_d={params['umap_d']}")
    return "\n".join(lines)
