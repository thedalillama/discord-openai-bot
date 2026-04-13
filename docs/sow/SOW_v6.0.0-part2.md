# SOW v6.0.0 — Conversation Segmentation Pipeline
# Part 2 of 3: Retrieval, Citations, Clustering Changes
# Status: IMPLEMENTED (2026-04-13)
# Branch: claude-code

---

## Retrieval Flow

### Current flow (message-based)
```
query → embed → find_relevant_clusters(cosine vs centroids)
  → get_cluster_messages(cluster_id) → raw messages
  → format with [N] labels → inject into context
```

### New flow (segment-based)
```
query → embed → find_relevant_clusters(cosine vs centroids)
  → get_cluster_segments(cluster_id) → segment syntheses
  → for each segment: get source messages → assign [N] labels
  → inject syntheses as context, source messages for citation map
```

Cluster centroids are now computed from segment embeddings. The
query embedding path is unchanged — `embed_query_with_smart_context()`
still embeds the user's query with conversational context.

### `cluster_retrieval.py` changes

**`find_relevant_clusters()`** — unchanged. Still loads centroids
from `clusters` table, computes cosine similarity, returns top-K.
Centroids are computed from segment embeddings during clustering
(stored in `clusters.embedding` as before).

**`get_cluster_messages()`** — replaced by `get_cluster_content()`:

```python
def get_cluster_content(cluster_id, exclude_ids=None):
    """Return segment syntheses and their source messages.

    Args:
        cluster_id: cluster to fetch content for
        exclude_ids: set of message IDs to exclude (recent messages)

    Returns list of dicts:
        [{"segment_id": str,
          "synthesis": str,
          "topic_label": str,
          "messages": [(msg_id, author, content, created_at), ...]}]
    """
```

SQL: join `cluster_segments` → `segments` → `segment_messages` →
`messages`. Order segments by `first_message_at`, messages within
each segment by `position`.

---

## Citation Mapping

Citations reference individual messages, not segments. This preserves
the existing citation UX — users see source messages in the footer.

### Context injection format

The context block sent to the LLM uses syntheses for comprehension
but labels source messages with [N] for citation:

```
[Topic: Database Selection]
Summary: Alice and Bob discussed database options. Bob recommended
PostgreSQL. Alice agreed. They also decided to use GCP free tier
for hosting.

Source messages:
[1] [2026-03-01] alice: Should we use PostgreSQL or SQLite?
[2] [2026-03-01] bob: PostgreSQL for sure
[3] [2026-03-01] alice: agreed

[Topic: Deployment Platform]
Summary: Bob asked about deployment. Alice suggested GCP free tier.
Bob agreed.

Source messages:
[4] [2026-03-01] bob: what about the deployment platform?
[5] [2026-03-01] alice: GCP, it's free tier
[6] [2026-03-01] bob: ok
```

The LLM sees BOTH the synthesis (for understanding) and the source
messages (for citation). The synthesis gives it the resolved meaning;
the [N] labels on source messages let it cite specific evidence.

### Citation map construction

In `_retrieve_cluster_context()` (context_retrieval.py):

```python
citation_map = {}
citation_num = 1
lines = []

for segment in get_cluster_content(cluster_id, exclude_ids):
    seg_lines = [f"[Topic: {segment['topic_label']}]"]
    seg_lines.append(f"Summary: {segment['synthesis']}")
    seg_lines.append("Source messages:")

    for msg_id, author, content, created_at in segment["messages"]:
        if msg_id in exclude_ids:
            continue
        citation_map[citation_num] = {
            "author": author, "content": content,
            "date": created_at or ""
        }
        seg_lines.append(
            f"[{citation_num}] [{(created_at or '')[:10]}] "
            f"{author}: {content}")
        citation_num += 1

    lines.append("\n".join(seg_lines))
```

### Token budget impact

Each segment now injects a synthesis (2-4 sentences) PLUS its source
messages. This uses more tokens per cluster than raw messages alone.
The partial cluster injection logic (v5.9.1) already handles budget
overflow — if a cluster's content exceeds the remaining budget,
messages are injected one by one until budget is hit.

Optimization: if budget is tight, inject ONLY the synthesis (no
source messages). Citations become unavailable for that segment but
comprehension is preserved. Implement this as a fallback when the
full segment+messages would exceed budget:

```python
if synthesis_only_mode:
    seg_lines = [f"[Topic: {segment['topic_label']}]"]
    seg_lines.append(segment['synthesis'])
    # No [N] labels, no citation map entries
```

---

## Clustering Changes

### `cluster_engine.py`

**`cluster_messages()`** → **`cluster_segments()`**

Input changes from message embeddings to segment embeddings. The
function signature changes:

```python
def cluster_segments(channel_id, min_cluster_size=None, min_samples=None):
    """Run UMAP + HDBSCAN on segment embeddings for a channel."""
```

Internally: load segment embeddings from `segments` table instead of
`message_embeddings`. UMAP and HDBSCAN logic is identical. Returns
the same structure: `{clusters: {label: {segment_ids, centroid}},
stats: {cluster_count, noise_count, ...}}`.

### `cluster_store.py`

**`run_clustering()`** — calls `cluster_segments()` instead of
`cluster_messages()`. Stores results in `cluster_segments` junction
table instead of `cluster_messages`.

**`store_cluster()`** — unchanged (stores centroid, label, timestamps).

**`get_cluster_stats()`** — counts segments per cluster instead of
messages per cluster.

### `cluster_summarizer.py`

**`summarize_cluster()`** — input changes. Currently loads raw
messages via `get_cluster_message_ids()` → `get_messages_by_ids()`.
New version loads segment syntheses via `get_cluster_segment_ids()`
→ `get_segments_by_ids()`.

The M-label format changes from raw messages to syntheses:

```python
# CURRENT:
# M1 author (2026-03-01): raw message content

# NEW:
# M1 [Database Selection]: Alice and Bob discussed database options...
```

The per-cluster Gemini prompt and structured output schema are
unchanged — it still extracts label, summary, decisions, key_facts,
action_items, open_questions. The input is just richer.

### `cluster_assign.py` (deferred)

Incremental assignment is deferred to v6.1.0. In v6.0.0, new
messages arriving between `!summary create` runs are still embedded
per-message (existing `raw_events.py` path) and assigned to clusters
via the current centroid assignment. This provides degraded but
functional retrieval until the next full rebuild.

---

## Smart Query Embedding

`embed_query_with_smart_context()` is unchanged. The query is still
embedded with conversational context from the in-memory history.

The query embedding now compares against segment-derived centroids
instead of message-derived centroids. Because segment embeddings are
denser and more semantically meaningful, the cosine similarity scores
should be higher and more discriminating — the same query should
produce a wider spread between relevant and irrelevant clusters.

---

*Continued in Part 3: File Changes, Testing, Success Criteria*
