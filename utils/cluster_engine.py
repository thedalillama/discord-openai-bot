# utils/cluster_engine.py
# Version 1.2.0
"""
UMAP + HDBSCAN clustering pipeline for v5.1.0.

Handles dimensionality reduction, clustering, noise reduction, and centroid
computation. All math lives here; SQLite CRUD lives in cluster_store.py.

CHANGES v1.2.0: Add _adaptive_params() — scale UMAP/HDBSCAN to input size
CHANGES v1.1.0: Add cluster_segments() — segment embeddings path (SOW v6.0.0)
CREATED v1.0.0: UMAP + HDBSCAN clustering pipeline (SOW v5.1.0)
- cluster_messages(): UMAP reduce, HDBSCAN cluster, noise reassignment, centroids
- Returns {clusters, noise_ids, stats} dict or None if too few embeddings
"""
import numpy as np
from utils.embedding_store import get_message_embeddings, cosine_similarity
from utils.logging_utils import get_logger
from config import (
    CLUSTER_MIN_CLUSTER_SIZE, CLUSTER_MIN_SAMPLES,
    UMAP_N_NEIGHBORS, UMAP_N_COMPONENTS, RETRIEVAL_MIN_SCORE)

logger = get_logger('cluster_engine')


def _adaptive_params(n, cfg_neighbors, cfg_min_cluster, cfg_min_samples, cfg_components):
    """Scale UMAP/HDBSCAN to input size; config values are treated as maximums."""
    n_neighbors = min(cfg_neighbors, max(3, int(n ** 0.5)))
    min_cluster_size = min(cfg_min_cluster, max(2, n // 20))
    min_samples = min(cfg_min_samples, max(1, min_cluster_size - 1))
    n_components = min(cfg_components, max(2, n.bit_length() - 2))
    return min(n_neighbors, n - 1), min_cluster_size, min_samples, n_components


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
    raw = get_message_embeddings(channel_id)
    if len(raw) < (min_cluster_size or CLUSTER_MIN_CLUSTER_SIZE):
        logger.info(f"ch:{channel_id}: {len(raw)} embeddings — too few to cluster")
        return None
    msg_ids = [r[0] for r in raw]
    vectors = np.array([r[1] for r in raw], dtype=np.float32)
    n_neighbors, mcs, ms, n_components = _adaptive_params(
        len(msg_ids), UMAP_N_NEIGHBORS, CLUSTER_MIN_CLUSTER_SIZE,
        CLUSTER_MIN_SAMPLES, UMAP_N_COMPONENTS)
    if min_cluster_size: mcs = min_cluster_size
    if min_samples: ms = min_samples
    logger.info(f"Adaptive ch:{channel_id} n={len(msg_ids)}: "
                f"neighbors={n_neighbors}, mcs={mcs}, ms={ms}, dims={n_components}")

    # --- UMAP reduction ---
    try:
        from umap import UMAP
        reduced = UMAP(
            n_neighbors=n_neighbors, n_components=n_components,
            min_dist=0.0, metric='cosine', random_state=42,
        ).fit_transform(vectors)
    except Exception as e:
        logger.warning(f"UMAP failed ch:{channel_id}: {e}")
        return None

    # --- HDBSCAN clustering ---
    try:
        from sklearn.cluster import HDBSCAN
        labels = HDBSCAN(
            min_cluster_size=mcs, min_samples=ms,
            metric='euclidean', cluster_selection_method='eom',
            store_centers='centroid', copy=False,
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


def cluster_segments(channel_id, min_cluster_size=None, min_samples=None):
    """UMAP + HDBSCAN on segment embeddings; same pipeline as cluster_messages().

    Returns {clusters (segment_ids), noise_ids, stats} or None if too few.
    """
    from utils.segment_store import get_segment_embeddings
    raw = get_segment_embeddings(channel_id)
    if len(raw) < (min_cluster_size or CLUSTER_MIN_CLUSTER_SIZE):
        logger.info(f"ch:{channel_id}: {len(raw)} segments — too few to cluster")
        return None
    seg_ids = [r[0] for r in raw]
    vectors  = np.array([r[1] for r in raw], dtype=np.float32)
    n_neighbors, mcs, ms, n_components = _adaptive_params(
        len(seg_ids), UMAP_N_NEIGHBORS, CLUSTER_MIN_CLUSTER_SIZE,
        CLUSTER_MIN_SAMPLES, UMAP_N_COMPONENTS)
    if min_cluster_size: mcs = min_cluster_size
    if min_samples: ms = min_samples
    logger.info(f"Adaptive ch:{channel_id} n={len(seg_ids)}: "
                f"neighbors={n_neighbors}, mcs={mcs}, ms={ms}, dims={n_components}")

    try:
        from umap import UMAP
        reduced = UMAP(
            n_neighbors=n_neighbors, n_components=n_components,
            min_dist=0.0, metric='cosine', random_state=42,
        ).fit_transform(vectors)
    except Exception as e:
        logger.warning(f"UMAP failed (segments) ch:{channel_id}: {e}")
        return None

    try:
        from sklearn.cluster import HDBSCAN
        labels = HDBSCAN(
            min_cluster_size=mcs, min_samples=ms,
            metric='euclidean', cluster_selection_method='eom',
            store_centers='centroid', copy=False,
        ).fit_predict(reduced)
    except Exception as e:
        logger.warning(f"HDBSCAN failed (segments) ch:{channel_id}: {e}")
        return None

    unique_labels = set(labels) - {-1}
    clusters = {}
    for lbl in unique_labels:
        idxs = np.where(labels == lbl)[0]
        clusters[int(lbl)] = {
            "indices":     idxs.tolist(),
            "segment_ids": [seg_ids[i] for i in idxs],
        }

    centroids = _compute_centroids(clusters, vectors)
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
            clusters[best_lbl]["segment_ids"].append(seg_ids[idx])
        else:
            remaining_noise.append(seg_ids[idx])

    centroids = _compute_centroids(clusters, vectors)
    for lbl in clusters:
        clusters[lbl]["centroid"] = centroids[lbl]
        del clusters[lbl]["indices"]

    total = len(seg_ids)
    largest = max((len(c["segment_ids"]) for c in clusters.values()), default=0)
    stats = {
        "total_messages":           total,
        "cluster_count":            len(clusters),
        "noise_count":              len(remaining_noise),
        "noise_ratio":              round(len(remaining_noise)/total, 4) if total else 0,
        "largest_cluster_size":     largest,
        "largest_cluster_fraction": round(largest/total, 4) if total else 0,
    }
    logger.info(f"Segment clustering ch:{channel_id}: {len(clusters)} clusters, "
                f"{len(remaining_noise)} noise")
    return {"clusters": clusters, "noise_ids": remaining_noise, "stats": stats}
