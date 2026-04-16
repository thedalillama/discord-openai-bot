# utils/cluster_retrieval.py
# Version 1.3.0
"""
Query-time cluster/segment/proposition retrieval for semantic context injection.

CHANGES v1.3.0: Proposition-level retrieval (SOW v6.3.0)
- ADD: find_relevant_propositions() — score query vs all proposition embeddings;
  collapse to max-score-per-segment before returning segment IDs for RRF input.
  Each segment appears at most once (no size bias from proposition count).

CHANGES v1.2.0: Direct segment retrieval (SOW v6.1.0)
- ADD: find_relevant_segments(), _apply_score_gap(), get_segment_with_messages()
- KEEP: find_relevant_clusters(), get_cluster_messages(), get_cluster_content()

CHANGES v1.1.0: Segment-aware retrieval (SOW v6.0.0)
CREATED v1.0.0: Cluster-based retrieval (SOW v5.5.0)
"""
import sqlite3
import numpy as np
from config import DATABASE_PATH
from utils.embedding_store import unpack_embedding
from utils.logging_utils import get_logger

logger = get_logger('cluster_retrieval')


def _apply_score_gap(results, gap_threshold=0.08):
    """Cut results at the largest score gap if it exceeds gap_threshold.

    Args:
        results: list of tuples where score is the last element.
        gap_threshold: minimum gap to trigger a cut (0 disables).

    Returns: pruned list (unchanged if no significant gap found).
    """
    if gap_threshold <= 0 or len(results) <= 1:
        return results
    gaps = [(results[i][-1] - results[i + 1][-1], i + 1)
            for i in range(len(results) - 1)]
    max_gap, cut_idx = max(gaps, key=lambda x: x[0])
    return results[:cut_idx] if max_gap >= gap_threshold else results


def find_relevant_segments(query_embedding, channel_id, top_k=5, floor=0.15):
    """Score query against all segment embeddings. Return top-K above floor.

    Queries segment embeddings directly instead of cluster centroids, giving
    focused similarity scores against individual topic groups.

    Args:
        query_embedding: query vector (list or np.array)
        channel_id: Discord channel ID
        top_k: max segments to return
        floor: absolute minimum score; segments below this are never returned

    Returns:
        list of (segment_id, topic_label, synthesis, score) tuples,
        score descending. Only segments above floor included.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        rows = conn.execute(
            "SELECT id, topic_label, synthesis, embedding FROM segments "
            "WHERE channel_id=? AND embedding IS NOT NULL",
            (channel_id,)).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    query = np.array(query_embedding, dtype=np.float32)
    results = []
    for seg_id, topic_label, synthesis, blob in rows:
        seg_vec = np.array(unpack_embedding(blob), dtype=np.float32)
        norm = float(np.linalg.norm(query) * np.linalg.norm(seg_vec))
        score = float(np.dot(query, seg_vec)) / norm if norm > 0 else 0.0
        if score >= floor:
            results.append((seg_id, topic_label or "", synthesis or "", score))

    results.sort(key=lambda x: x[3], reverse=True)
    return results[:top_k]


def get_segment_with_messages(segment_id, exclude_ids=None):
    """Return synthesis and source messages for a single segment.

    Placed here (not segment_store.py) due to the 250-line limit on that file.

    Returns:
        {"segment_id", "topic_label", "synthesis",
         "messages": [(msg_id, author, content, created_at), ...]}
        or None if segment not found.
    """
    exclude = set(exclude_ids or [])
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        row = conn.execute(
            "SELECT id, topic_label, synthesis FROM segments WHERE id=?",
            (segment_id,)).fetchone()
        if not row:
            return None
        seg_id, topic_label, synthesis = row
        msgs = conn.execute(
            "SELECT m.id, m.author_name, m.content, m.created_at "
            "FROM segment_messages sm JOIN messages m ON m.id=sm.message_id "
            "WHERE sm.segment_id=? ORDER BY sm.position ASC",
            (seg_id,)).fetchall()
        return {
            "segment_id":  seg_id,
            "topic_label": topic_label or "",
            "synthesis":   synthesis or "",
            "messages":    [(r[0], r[1], r[2], r[3])
                            for r in msgs if r[0] not in exclude],
        }
    finally:
        conn.close()


def find_relevant_propositions(query_embedding, channel_id, top_k=10, floor=0.20):
    """Score query vs proposition embeddings; collapse to segment IDs.

    Each segment gets at most one entry — the highest-scoring proposition
    per segment. This prevents size bias: a segment with 5 propositions
    does not outrank one with 2 simply by having more entries in RRF.

    Args:
        query_embedding: query vector (list or np.array)
        channel_id: Discord channel ID
        top_k: max segment IDs to return
        floor: minimum proposition score; propositions below this are ignored

    Returns:
        list of (segment_id, best_score) tuples, score descending.
        Returns [] if no propositions exist (degrades to dense+BM25).
    """
    from utils.proposition_store import get_proposition_embeddings
    rows = get_proposition_embeddings(channel_id)
    if not rows:
        return []
    query = np.array(query_embedding, dtype=np.float32)
    seg_best = {}
    for _, seg_id, _, vec in rows:
        vec_arr = np.array(vec, dtype=np.float32)
        norm = float(np.linalg.norm(query) * np.linalg.norm(vec_arr))
        score = float(np.dot(query, vec_arr)) / norm if norm > 0 else 0.0
        if score >= floor and score > seg_best.get(seg_id, -1):
            seg_best[seg_id] = score
    results = sorted(seg_best.items(), key=lambda x: x[1], reverse=True)
    return results[:top_k]


def find_relevant_clusters(query_embedding, channel_id, top_k=5):
    """Return top-K (cluster_id, label, score) sorted by cosine similarity.

    Loads all cluster centroids for the channel. Retained for rollback
    path and !debug commands.
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

    Retained for rollback path and !explain detail.
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


def get_cluster_content(cluster_id, exclude_ids=None):
    """Return segment syntheses and source messages for a cluster.

    Delegates to segment_store.get_cluster_content(). Retained for rollback.
    Returns empty list if no segments exist.
    """
    from utils.segment_store import get_cluster_content as _get
    return _get(cluster_id, exclude_ids)
