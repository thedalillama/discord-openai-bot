# SOW v5.1.0 — Schema + HDBSCAN Clustering Core
# Part 1 of 2: Objective, Schema, Clustering Module
# Status: APPROVED
# Branch: claude-code
# Prerequisite: v4.1.10 (semantic retrieval with timestamps)

---

## Objective

Implement the UMAP + HDBSCAN clustering pipeline that groups existing
message embeddings into semantically coherent clusters. This phase
creates the schema, the clustering module, and a diagnostic command
to validate cluster quality. **No LLM calls. No changes to the bot's
response pipeline.** The existing v4.1.x summarization and retrieval
continue to work unchanged.

This is the foundation for v5.0.0. If clusters are bad, nothing
downstream works. This phase exists to validate and tune clustering
parameters before building summarization on top.

---

## Context

The research report ("Embedding-Based Clustering for Conversational
Summarization") recommends HDBSCAN with UMAP preprocessing as the
core clustering approach, following the BERTopic-validated pipeline.
Key findings:

- **HDBSCAN over DBSCAN**: Eliminates fixed eps tuning; handles
  varying cluster sizes (5 messages to 100+) automatically.
- **UMAP preprocessing is critical**: Clustering directly on 1536
  dimensions produces worse results. UMAP reduces to 5 dimensions
  while preserving local and global structure.
- **Noise is the biggest challenge**: HDBSCAN on short chat messages
  may classify 30-50% as noise. Embedding-based noise reduction is
  essential.
- **Full re-clustering is correct** at our scale (sub-second for 10K
  messages after UMAP). No incremental approach needed.
- **scikit-learn 1.3+ includes HDBSCAN natively** — no standalone
  hdbscan package required.

---

## Dependencies to Install

```bash
pip install scikit-learn umap-learn --break-system-packages
```

Add to `requirements.txt` (create if needed):
```
scikit-learn>=1.3
umap-learn>=0.5
```

These bring numpy, scipy, joblib, pynndescent, numba, llvmlite.
Total ~300 MB installed. Verify installation succeeds on the GCP VM
before writing any code.

---

## Schema: `schema/005.sql`

Two new tables. Does NOT modify or drop any existing tables.

```sql
-- v5.0.0 — Cluster-based summarization tables

CREATE TABLE IF NOT EXISTS clusters (
    id TEXT PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    embedding BLOB,
    message_count INTEGER DEFAULT 0,
    first_message_at TEXT,
    last_message_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cluster_channel
    ON clusters(channel_id);

CREATE TABLE IF NOT EXISTS cluster_messages (
    cluster_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    PRIMARY KEY (cluster_id, message_id),
    FOREIGN KEY (cluster_id) REFERENCES clusters(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);
```

The `embedding` column stores the cluster centroid (normalized mean
of member embeddings) as a packed BLOB, using the same `pack_embedding`
/ `unpack_embedding` functions from `embedding_store.py`.

Cluster IDs follow the pattern `cluster-{channel_id}-{n}` where n
is the HDBSCAN label (0, 1, 2, ...). The noise cluster (label -1) is
NOT stored — noise points remain in `message_embeddings` for fallback
retrieval but do not get a row in `clusters`.

---

## New Module: `utils/cluster_store.py`

This is the core deliverable. It must stay under **250 lines**. If it
exceeds that, split HDBSCAN + UMAP logic into a separate file
(e.g., `utils/cluster_engine.py`) and keep CRUD + retrieval in
`cluster_store.py`.

### Functions Required

#### Clustering

```python
def cluster_messages(channel_id, min_cluster_size=None, min_samples=None):
    """Run UMAP + HDBSCAN on all message embeddings for a channel.

    Pipeline:
    1. Load all embeddings from message_embeddings (via embedding_store)
    2. Convert to numpy array
    3. UMAP reduce: 1536 dims → UMAP_N_COMPONENTS dims
    4. HDBSCAN cluster on reduced embeddings
    5. Noise reduction: assign noise points to nearest cluster centroid
       if cosine similarity > RETRIEVAL_MIN_SCORE (0.25)
    6. Compute centroids: normalized mean of member embeddings
       (use ORIGINAL 1536-dim embeddings for centroids, not UMAP-reduced)
    7. Return results dict

    Returns:
        {
            "clusters": {
                0: {"message_ids": [...], "centroid": np.array(1536)},
                1: {"message_ids": [...], "centroid": np.array(1536)},
                ...
            },
            "noise_ids": [...],  # unassigned after noise reduction
            "stats": {
                "total_messages": int,
                "cluster_count": int,
                "noise_count": int,
                "noise_ratio": float,
                "largest_cluster_size": int,
                "largest_cluster_fraction": float,
            }
        }

    Returns None if fewer than min_cluster_size embeddings exist.
    """
```

**UMAP configuration** (BERTopic defaults, adjusted for small corpora):
```python
from umap import UMAP

umap_model = UMAP(
    n_neighbors=UMAP_N_NEIGHBORS,   # default 15; lower to 10 for <1000 msgs
    n_components=UMAP_N_COMPONENTS,  # default 5
    min_dist=0.0,                    # critical: tight clumps for HDBSCAN
    metric='cosine',                 # correct for OpenAI embeddings
    random_state=42                  # reproducibility
)
reduced = umap_model.fit_transform(vectors)
```

**HDBSCAN configuration**:
```python
from sklearn.cluster import HDBSCAN

clusterer = HDBSCAN(
    min_cluster_size=min_cluster_size,  # default 5
    min_samples=min_samples,            # default 3
    metric='euclidean',                 # correct post-UMAP
    cluster_selection_method='eom',     # Excess of Mass (default)
    store_centers='centroid'            # sklearn stores centroids
)
labels = clusterer.fit_predict(reduced)
```

**Noise reduction** (after HDBSCAN, before storage):
```python
# For each noise point (label == -1):
# 1. Compute cosine similarity to each cluster centroid
#    (using ORIGINAL 1536-dim embeddings, not UMAP-reduced)
# 2. If best similarity > RETRIEVAL_MIN_SCORE: assign to that cluster
# 3. Otherwise: remains noise
```

**Centroid computation** (using ORIGINAL 1536-dim embeddings):
```python
import numpy as np

# For each cluster, compute mean of member embeddings, then normalize
member_vecs = vectors[member_indices]
centroid = np.mean(member_vecs, axis=0)
centroid = centroid / np.linalg.norm(centroid)  # L2 normalize
```

**Important**: Centroids are computed from the original 1536-dim
embeddings, NOT the UMAP-reduced embeddings. UMAP reduction is for
clustering only. Centroids must be in the same space as query
embeddings for retrieval to work.

#### Storage (CRUD)

```python
def store_cluster(channel_id, cluster_label, centroid, message_ids,
                  first_at, last_at):
    """Store a cluster with its centroid and message membership.
    Uses pack_embedding() from embedding_store for the centroid BLOB.
    Cluster ID format: 'cluster-{channel_id}-{cluster_label}'
    """

def clear_channel_clusters(channel_id):
    """Delete all clusters and cluster_messages for a channel.
    Called before storing fresh clusters (same pattern as
    clear_channel_topics in embedding_store.py).
    """

def get_cluster_stats(channel_id):
    """Return cluster diagnostics for !debug clusters.
    Returns list of dicts with: cluster_id, label, message_count,
    first_message_at, last_message_at, status.
    Also returns total message count and noise count.
    """
```

### What This Module Does NOT Do (Yet)

- No `find_relevant_clusters()` — that's Phase 4
- No `get_cluster_messages()` — that's Phase 4
- No LLM calls — that's Phase 2
- No changes to `context_manager.py` — that's Phase 4
- No changes to `summarizer.py` — that's Phase 3

---

*Continued in Part 2: Config, Commands, Testing, File Summary*
