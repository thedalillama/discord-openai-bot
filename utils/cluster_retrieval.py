# utils/cluster_retrieval.py
# Version 1.0.0
"""
Query-time cluster retrieval for semantic context injection.

Called from context_manager.py to find relevant clusters for an incoming
query and fetch their member messages for injection into the system prompt.
Mirrors find_relevant_topics()/get_topic_messages() from embedding_store.py
but reads from clusters/cluster_messages instead of topics/topic_messages.

CREATED v1.0.0: Cluster-based retrieval replacing topic retrieval (SOW v5.5.0)
- find_relevant_clusters(): cosine similarity vs channel cluster centroids
- get_cluster_messages(): member messages for a given cluster
"""
import sqlite3
import numpy as np
from config import DATABASE_PATH
from utils.embedding_store import unpack_embedding
from utils.logging_utils import get_logger

logger = get_logger('cluster_retrieval')


def find_relevant_clusters(query_embedding, channel_id, top_k=5):
    """Return top-K (cluster_id, label, score) sorted by cosine similarity.

    Loads all cluster centroids for the channel, scores each against the
    query vector. No noise filter needed — HDBSCAN noise points never form
    clusters, so there are no noise clusters to filter.

    Args:
        query_embedding: list or array of floats (query message vector)
        channel_id: Discord channel ID
        top_k: max clusters to return (caller applies RETRIEVAL_MIN_SCORE)

    Returns: list of (cluster_id, label, score) tuples, score descending.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id, label, embedding FROM clusters "
            "WHERE channel_id=? AND embedding IS NOT NULL",
            (channel_id,)).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    query = np.array(query_embedding, dtype=np.float32)
    results = []
    for cluster_id, label, blob in rows:
        centroid = np.array(unpack_embedding(blob), dtype=np.float32)
        norm = float(np.linalg.norm(query) * np.linalg.norm(centroid))
        score = float(np.dot(query, centroid)) / norm if norm > 0 else 0.0
        results.append((cluster_id, label or "", score))

    results.sort(key=lambda x: x[2], reverse=True)
    return results[:top_k]


def get_cluster_messages(cluster_id, exclude_ids=None):
    """Return (message_id, author_name, content, created_at) for a cluster.

    Messages ordered by created_at ascending. Messages in exclude_ids are
    omitted to prevent duplication with recent conversation context.

    Args:
        cluster_id: cluster identifier string
        exclude_ids: set/collection of message_ids already in conversation context

    Returns: list of (message_id, author_name, content, created_at) tuples.
    """
    exclude = set(exclude_ids) if exclude_ids else set()
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT cm.message_id, m.author_name, m.content, m.created_at "
            "FROM cluster_messages cm "
            "JOIN messages m ON m.id=cm.message_id "
            "WHERE cm.cluster_id=? ORDER BY m.created_at ASC",
            (cluster_id,)).fetchall()
        return [(r[0], r[1], r[2], r[3]) for r in rows if r[0] not in exclude]
    finally:
        conn.close()
