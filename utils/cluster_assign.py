# utils/cluster_assign.py
# Version 1.0.0
"""
On-arrival cluster assignment for incremental message routing.

When a new message is embedded, compare its vector against existing cluster
centroids for the channel. If a match is found (cosine similarity >=
RETRIEVAL_MIN_SCORE), assign the message to that cluster, update the centroid
via running average + renormalize, and mark the cluster dirty.

Called from raw_events.py after embed_and_store_message() succeeds.
Synchronous — use asyncio.to_thread() in async callers.

CREATED v1.0.0: Incremental cluster assignment (SOW v5.4.0)
"""
import sqlite3
import numpy as np
from config import DATABASE_PATH, RETRIEVAL_MIN_SCORE
from utils.embedding_store import pack_embedding, unpack_embedding
from utils.logging_utils import get_logger

logger = get_logger('cluster_assign')


def _cosine_similarity(a, b):
    """Cosine similarity between two unit-norm numpy arrays."""
    dot = float(np.dot(a, b))
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    return dot / norm if norm > 0 else 0.0


def _load_message_embedding(message_id):
    """Return numpy float32 array for message_id, or None."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT embedding FROM message_embeddings WHERE message_id=?",
            (message_id,)).fetchone()
        if row is None or row[0] is None:
            return None
        return np.array(unpack_embedding(row[0]), dtype=np.float32)
    finally:
        conn.close()


def _load_cluster_centroids(channel_id):
    """Return list of (cluster_id, centroid_array, message_count)."""
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id, embedding, message_count FROM clusters "
            "WHERE channel_id=? AND embedding IS NOT NULL",
            (channel_id,)).fetchall()
        results = []
        for cluster_id, blob, mc in rows:
            vec = np.array(unpack_embedding(blob), dtype=np.float32)
            results.append((cluster_id, vec, mc))
        return results
    finally:
        conn.close()


def _update_and_assign(cluster_id, message_id, old_centroid, new_vec, old_n):
    """Insert message into cluster, update centroid, mark needs_resummarize."""
    new_n = old_n + 1
    updated = (old_centroid * old_n + new_vec) / new_n
    magnitude = np.linalg.norm(updated)
    if magnitude > 0:
        updated = updated / magnitude
    new_blob = pack_embedding(updated.tolist())

    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO cluster_messages(cluster_id, message_id)"
            " VALUES (?,?)",
            (cluster_id, message_id))
        conn.execute(
            "UPDATE clusters SET embedding=?, message_count=?,"
            " needs_resummarize=1, updated_at=datetime('now') WHERE id=?",
            (new_blob, new_n, cluster_id))
        conn.commit()
        logger.debug(
            f"Assigned msg:{message_id} → cluster:{cluster_id} (n={new_n})")
    finally:
        conn.close()


def assign_to_nearest_cluster(channel_id, message_id):
    """
    Assign message to nearest cluster centroid if score >= RETRIEVAL_MIN_SCORE.

    Synchronous — call via asyncio.to_thread() from async context.
    Returns True if assigned, False if no clusters exist or score too low.
    """
    vec = _load_message_embedding(message_id)
    if vec is None:
        logger.debug(f"No embedding for msg:{message_id}, skipping assignment")
        return False

    centroids = _load_cluster_centroids(channel_id)
    if not centroids:
        return False

    best_id, best_centroid, best_n = None, None, 0
    best_score = -1.0
    for cluster_id, centroid, mc in centroids:
        score = _cosine_similarity(vec, centroid)
        if score > best_score:
            best_score = score
            best_id = cluster_id
            best_centroid = centroid
            best_n = mc

    if best_score < RETRIEVAL_MIN_SCORE:
        logger.debug(
            f"msg:{message_id} best_score={best_score:.3f} below threshold,"
            f" no assignment")
        return False

    _update_and_assign(best_id, message_id, best_centroid, vec, best_n)
    return True
