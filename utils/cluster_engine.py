# utils/cluster_engine.py
# Version 1.0.1
"""
UMAP + HDBSCAN clustering pipeline for v5.1.0.

Handles dimensionality reduction, clustering, noise reduction, and centroid
computation. All math lives here; SQLite CRUD lives in cluster_store.py.

CREATED v1.0.0: UMAP + HDBSCAN clustering pipeline (SOW v5.1.0)
- cluster_messages(): full pipeline — load embeddings, UMAP reduce,
  HDBSCAN cluster, noise reassignment, centroid computation
- Returns result dict with clusters, noise_ids, and stats
- Returns None if fewer than min_cluster_size embeddings exist
"""
import numpy as np
from utils.embedding_store import get_message_embeddings, cosine_similarity
from utils.logging_utils import get_logger
from config import (
    CLUSTER_MIN_CLUSTER_SIZE, CLUSTER_MIN_SAMPLES,
    UMAP_N_NEIGHBORS, UMAP_N_COMPONENTS, RETRIEVAL_MIN_SCORE)

logger = get_logger('cluster_engine')


def cluster_messages(channel_id, min_cluster_size=None, min_samples=None):
    """Run UMAP + HDBSCAN on all message embeddings for a channel.

    Pipeline:
    1. Load embeddings from message_embeddings via embedding_store
    2. UMAP: 1536 dims → UMAP_N_COMPONENTS dims (cosine metric)
    3. HDBSCAN on reduced embeddings (euclidean metric)
    4. Noise reduction: reassign noise points to nearest centroid
       if cosine similarity > RETRIEVAL_MIN_SCORE
    5. Compute centroids from ORIGINAL 1536-dim embeddings (normalized mean)

    Returns dict with 'clusters', 'noise_ids', 'stats', or None if
    fewer than min_cluster_size embeddings exist.
    """
    mcs = min_cluster_size or CLUSTER_MIN_CLUSTER_SIZE
    ms  = min_samples      or CLUSTER_MIN_SAMPLES

    raw = get_message_embeddings(channel_id)
    if len(raw) < mcs:
        logger.info(
            f"ch:{channel_id} has {len(raw)} embeddings — "
            f"need at least {mcs} to cluster")
        return None

    msg_ids = [r[0] for r in raw]
    vectors = np.array([r[1] for r in raw], dtype=np.float32)
    logger.info(
        f"Clustering ch:{channel_id}: {len(msg_ids)} msgs, "
        f"min_cluster_size={mcs}, min_samples={ms}, "
        f"umap_neighbors={UMAP_N_NEIGHBORS}, umap_dims={UMAP_N_COMPONENTS}")

    # --- UMAP reduction ---
    try:
        from umap import UMAP
        n_neighbors = min(UMAP_N_NEIGHBORS, len(msg_ids) - 1)
        reduced = UMAP(
            n_neighbors=n_neighbors,
            n_components=UMAP_N_COMPONENTS,
            min_dist=0.0,
            metric='cosine',
            random_state=42
        ).fit_transform(vectors)
    except Exception as e:
        logger.warning(f"UMAP failed ch:{channel_id}: {e}")
        return None

    # --- HDBSCAN clustering ---
    try:
        from sklearn.cluster import HDBSCAN
        labels = HDBSCAN(
            min_cluster_size=mcs,
            min_samples=ms,
            metric='euclidean',
            cluster_selection_method='eom',
            store_centers='centroid',
            copy=False,
        ).fit_predict(reduced)
    except Exception as e:
        logger.warning(f"HDBSCAN failed ch:{channel_id}: {e}")
        return None

    unique_labels = set(labels) - {-1}
    logger.info(
        f"HDBSCAN raw: {len(unique_labels)} clusters, "
        f"{(labels == -1).sum()} noise points")

    # --- Initial cluster membership (original 1536-dim) ---
    clusters = {}
    for lbl in unique_labels:
        idxs = np.where(labels == lbl)[0]
        clusters[int(lbl)] = {
            "indices": idxs.tolist(),
            "message_ids": [msg_ids[i] for i in idxs],
        }

    # --- Compute initial centroids (original space) ---
    centroids = _compute_centroids(clusters, vectors)

    # --- Noise reduction ---
    noise_idxs = np.where(labels == -1)[0]
    remaining_noise = []
    for idx in noise_idxs:
        vec = vectors[idx].tolist()
        best_lbl, best_score = None, -1.0
        for lbl, centroid in centroids.items():
            score = cosine_similarity(vec, centroid.tolist())
            if score > best_score:
                best_lbl, best_score = lbl, score
        if best_score >= RETRIEVAL_MIN_SCORE and best_lbl is not None:
            clusters[best_lbl]["indices"].append(idx)
            clusters[best_lbl]["message_ids"].append(msg_ids[idx])
            logger.debug(
                f"Noise msg {msg_ids[idx]} reassigned to cluster "
                f"{best_lbl} (score {best_score:.3f})")
        else:
            remaining_noise.append(msg_ids[idx])

    # --- Recompute centroids after reassignment ---
    centroids = _compute_centroids(clusters, vectors)
    for lbl in clusters:
        clusters[lbl]["centroid"] = centroids[lbl]
        del clusters[lbl]["indices"]

    noise_ratio = len(remaining_noise) / len(msg_ids)
    if noise_ratio > 0.3:
        logger.warning(
            f"High noise ratio ch:{channel_id}: "
            f"{noise_ratio:.1%} ({len(remaining_noise)} msgs)")

    sizes = [len(c["message_ids"]) for c in clusters.values()]
    largest = max(sizes) if sizes else 0
    stats = {
        "total_messages":         len(msg_ids),
        "cluster_count":          len(clusters),
        "noise_count":            len(remaining_noise),
        "noise_ratio":            round(noise_ratio, 4),
        "largest_cluster_size":   largest,
        "largest_cluster_fraction": round(largest / len(msg_ids), 4) if msg_ids else 0,
    }
    logger.info(
        f"Clustering complete ch:{channel_id}: {stats['cluster_count']} clusters, "
        f"{stats['noise_count']} noise ({stats['noise_ratio']:.1%})")

    return {"clusters": clusters, "noise_ids": remaining_noise, "stats": stats}


def _compute_centroids(clusters, vectors):
    """Compute normalized mean centroid for each cluster (original space)."""
    centroids = {}
    for lbl, data in clusters.items():
        idxs = data["indices"]
        member_vecs = vectors[idxs]
        centroid = np.mean(member_vecs, axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        centroids[lbl] = centroid
    return centroids
