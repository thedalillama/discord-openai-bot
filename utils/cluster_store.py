# utils/cluster_store.py
# Version 1.1.0
"""
SQLite CRUD and orchestration for v5.1.0 cluster-based summarization.

Handles storage, retrieval, and diagnostic formatting for clusters.
Clustering math (UMAP + HDBSCAN) lives in cluster_engine.py.

CHANGES v1.1.0: Add CRUD helpers for v5.2.0 per-cluster summarization
- ADDED: get_cluster_message_ids() — ordered message IDs for a cluster
- ADDED: get_clusters_for_channel() — all clusters for summarization loop
- ADDED: update_cluster_label_summary() — store LLM-generated fields
- ADDED: get_messages_by_ids() — fetch message content for LLM input
  (added here instead of message_store.py which is at 254 lines)

CREATED v1.0.0: Cluster CRUD, orchestration, diagnostics (SOW v5.1.0)
- store_cluster(): upsert cluster + member links
- clear_channel_clusters(): delete-before-insert
- get_cluster_stats(): diagnostics for !debug clusters
- run_clustering(): orchestrator — cluster → clear → store
- format_cluster_report(): Discord-ready output string
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

    # Fetch created_at for all messages so we can record date ranges
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


def format_cluster_report(channel_name, stats, cluster_rows, params):
    """Format !debug clusters output for Discord."""
    total  = stats["total_messages"]
    count  = stats["cluster_count"]
    noise  = stats["noise_count"]
    pct    = stats["noise_ratio"] * 100
    largest = stats["largest_cluster_size"]
    largest_pct = stats["largest_cluster_fraction"] * 100

    lines = [
        f"ℹ️ **Cluster Analysis** (channel: #{channel_name})",
        f"Messages: {total} total, {count} clusters, "
        f"{noise} noise ({pct:.1f}%)",
        f"Largest cluster: {largest} msgs ({largest_pct:.1f}%)",
        "",
    ]
    for i, row in enumerate(cluster_rows):
        first = (row["first_message_at"] or "")[:10]
        last  = (row["last_message_at"]  or "")[:10]
        date_range = f"{first} – {last}" if first else "no dates"
        lines.append(
            f"Cluster {i}: {row['message_count']} msgs ({date_range})")
    lines.append(f"Noise: {noise} msgs unassigned")
    lines.append("")
    lines.append(
        f"Parameters: min_cluster_size={params['mcs']}, "
        f"min_samples={params['ms']}, "
        f"umap_n={params['umap_n']}, "
        f"umap_d={params['umap_d']}")
    return "\n".join(lines)
