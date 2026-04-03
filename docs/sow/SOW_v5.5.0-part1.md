# SOW v5.5.0 — Cluster-Based Retrieval Integration
# Part 1 of 2: Objective, Design, Cluster Retrieval Functions
# Status: PROPOSED — awaiting approval
# Branch: claude-code
# Prerequisite: v5.4.0 (three-tier incremental updates)

---

## Objective

Replace topic-based semantic retrieval with cluster-based retrieval
in the bot's response path. When a user sends a message, the bot
embeds it, finds the most relevant clusters by centroid similarity,
and injects those clusters' member messages into the context. This
is the final piece that makes the v5 cluster pipeline user-facing.

After v5.5.0, the full v5 architecture is live: messages are
clustered on arrival (Tier 1), clusters are summarized on demand
(Tier 2/3), and retrieval uses cluster centroids to surface
relevant past conversations in every bot response.

---

## What Changes

The retrieval path lives in `_retrieve_topic_context()` in
`utils/context_manager.py`. Currently it:

1. Embeds the latest user message (`embed_text()`)
2. Finds relevant topics (`find_relevant_topics()`)
3. Fetches linked messages (`get_topic_messages()`)
4. Falls back to direct message search (`find_similar_messages()`)

v5.5.0 swaps steps 2 and 3:

1. Embeds the latest user message — **unchanged**
2. Finds relevant clusters (`find_relevant_clusters()`) — **NEW**
3. Fetches cluster member messages (`get_cluster_messages()`) — **NEW**
4. Falls back to direct message search — **unchanged**

The function signature, return format, token budget logic, timestamp
prefixing, today's date injection, and the `build_context_for_provider`
caller are all unchanged.

---

## Cluster Retrieval Functions

These may already exist in `cluster_store.py` from earlier phases.
If not, add them. If they exist, verify the signatures match.

### `find_relevant_clusters(query_embedding, channel_id, top_k=5)`

Load all cluster centroids for the channel. Compute cosine similarity
between the query embedding and each centroid. Return the top-K
clusters sorted by score descending.

```python
def find_relevant_clusters(query_embedding, channel_id, top_k=5):
    """Return top-K (cluster_id, label, score) by cosine similarity
    against cluster centroids.

    Unlike find_relevant_topics(), no noise filter needed — HDBSCAN
    noise points don't form clusters, so there are no noise clusters
    to filter.
    """
```

Returns: list of `(cluster_id, label, score)` tuples.

**Implementation**: Load centroids from the `clusters` table
(`SELECT id, label, embedding FROM clusters WHERE channel_id=? AND
embedding IS NOT NULL`), unpack each embedding BLOB, compute cosine
similarity against the query vector, sort descending, return top-K.

This mirrors `find_relevant_topics()` in `embedding_store.py` but
reads from `clusters` instead of `topics`.

### `get_cluster_messages(cluster_id, exclude_ids=None)`

Fetch all messages belonging to a cluster, ordered by timestamp.

```python
def get_cluster_messages(cluster_id, exclude_ids=None):
    """Return (message_id, author_name, content, created_at) for
    cluster member messages. Ordered by created_at ascending.
    Excludes messages in exclude_ids (recent messages already in
    conversation context).
    """
```

Returns: list of `(message_id, author_name, content, created_at)`.

**Implementation**: Join `cluster_messages` with `messages` on
`message_id`, filter by `cluster_id`, exclude `exclude_ids`, order
by `created_at ASC`.

This mirrors `get_topic_messages()` in `embedding_store.py` but
reads from `cluster_messages` instead of `topic_messages`.

---

## Changes to `context_manager.py`

Rename `_retrieve_topic_context()` to `_retrieve_cluster_context()`
(or keep the name and change the internals — either is fine).

### Import Changes

Replace:
```python
from utils.embedding_store import (
    embed_text, find_relevant_topics, get_topic_messages)
```

With:
```python
from utils.embedding_store import embed_text
from utils.cluster_store import (
    find_relevant_clusters, get_cluster_messages)
```

`embed_text` stays in `embedding_store.py`. `find_similar_messages`
stays in `embedding_store.py` (fallback path unchanged).

### Retrieval Logic Changes

The structure is identical — swap function names and adjust the
log messages:

```python
# Before (v4.x topics):
topics = find_relevant_topics(query_vec, channel_id, top_k=RETRIEVAL_TOP_K)
topics = [(tid, title, s) for tid, title, s in topics
          if s >= RETRIEVAL_MIN_SCORE]
...
msgs = get_topic_messages(topic_id, exclude_ids=recent_ids)
section = f"[Topic: {title}]\n" + ...

# After (v5.x clusters):
clusters = find_relevant_clusters(query_vec, channel_id,
                                   top_k=RETRIEVAL_TOP_K)
clusters = [(cid, label, s) for cid, label, s in clusters
            if s >= RETRIEVAL_MIN_SCORE]
...
msgs = get_cluster_messages(cluster_id, exclude_ids=recent_ids)
section = f"[Topic: {label}]\n" + ...
```

Note: the section header still says `[Topic: {label}]` — this is
what the conversation LLM sees, and "Topic" is a better framing
than "Cluster" for the model's understanding.

### Context Block Framing

The `--- PAST MESSAGES FROM THIS CHANNEL ---` header and framing
text remain unchanged. The LLM doesn't need to know these came
from clusters instead of topics.

---

## What Does NOT Change

- `build_context_for_provider()` — unchanged (calls the retrieval
  function internally)
- `_fallback_msg_search()` — unchanged (still uses
  `find_similar_messages` from `embedding_store.py`)
- `_load_summary()` — unchanged
- `format_always_on_context()` — unchanged
- `format_summary_for_context()` — unchanged
- Token budget logic — unchanged
- Timestamp prefixing (`[YYYY-MM-DD]`) — unchanged
- Today's date injection — unchanged
- `MAX_RECENT_MESSAGES` cap — unchanged
- All existing config variables — unchanged

---

*Continued in Part 2: Testing, File Summary, Documentation*
