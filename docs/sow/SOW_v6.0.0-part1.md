# SOW v6.0.0 — Conversation Segmentation Pipeline
# Part 1 of 3: Architecture, Schema, Segmentation + Synthesis
# Status: IMPLEMENTED (2026-04-13)
# Branch: claude-code
# Prerequisite: v5.13.0 (embedding noise filter)

---

## Problem Statement

The bot embeds individual messages as the retrieval unit. Short
messages produce thin embeddings that cluster by form rather than
meaning. Benchmark baseline (v5.13.0): avg top score 0.377, keyword
recall 19%, abstract query scores 0.29–0.37.

## Objective

Replace per-message embedding with per-segment embedding. A segment
is a topically coherent group of consecutive messages with an
LLM-generated synthesis that resolves all implicit meaning.

```
CURRENT:  message → context-prepend → embed → UMAP+HDBSCAN → summarize
NEW:      messages → segment+synthesize → embed → UMAP+HDBSCAN → summarize
```

## Architecture Overview

### Pipeline (batch mode, `!summary create`)

```
1. Load non-noise messages for channel
2. Segment + synthesize via Gemini (combined call)
3. Embed each synthesis via OpenAI
4. Store segments in DB
5. UMAP + HDBSCAN on segment embeddings
6. Store clusters referencing segments
7. Per-cluster summarization (sends syntheses)
8. Classifier → overview → dedup → QA → save
```

Steps 1, 5, 7-8 are structurally unchanged. Steps 2-4, 6 are new.

### Rollback

`message_embeddings` and `cluster_messages` tables retained. If
segmentation produces worse results, revert `summarizer.py` routing
and run `!summary create` to rebuild with message-based clustering.

---

## Schema: `schema/008.sql`

```sql
-- schema/008.sql
-- v6.0.0: Conversation segmentation tables

CREATE TABLE IF NOT EXISTS segments (
    id               TEXT PRIMARY KEY,
    channel_id       INTEGER NOT NULL,
    topic_label      TEXT,
    synthesis        TEXT NOT NULL,
    embedding        BLOB,
    message_count    INTEGER NOT NULL,
    first_message_id INTEGER NOT NULL,
    last_message_id  INTEGER NOT NULL,
    first_message_at TEXT,
    last_message_at  TEXT,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_segments_channel
    ON segments(channel_id);

CREATE TABLE IF NOT EXISTS segment_messages (
    segment_id TEXT    NOT NULL,
    message_id INTEGER NOT NULL,
    position   INTEGER NOT NULL,
    PRIMARY KEY (segment_id, message_id),
    FOREIGN KEY (segment_id) REFERENCES segments(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);
CREATE INDEX IF NOT EXISTS idx_segment_messages_message
    ON segment_messages(message_id);

CREATE TABLE IF NOT EXISTS cluster_segments (
    cluster_id TEXT NOT NULL,
    segment_id TEXT NOT NULL,
    PRIMARY KEY (cluster_id, segment_id),
    FOREIGN KEY (cluster_id) REFERENCES clusters(id),
    FOREIGN KEY (segment_id) REFERENCES segments(id)
);
```

`message_embeddings`, `cluster_messages` NOT dropped — rollback safe.

---

## Segmentation + Synthesis: Combined Gemini Call

A single Gemini Flash Lite call per batch identifies segment
boundaries AND produces a synthesis for each segment. This halves
API calls vs separate segmentation and synthesis steps.

### Input format

Messages batched in groups of ~500 (SUMMARIZER_BATCH_SIZE). Each
message formatted with index, timestamp, author, and content:

```
[0] [2026-03-01 14:00] alice: Should we use PostgreSQL or SQLite?
[1] [2026-03-01 14:01] bob: PostgreSQL for sure
[2] [2026-03-01 14:01] alice: agreed
[3] [2026-03-01 14:05] bob: what about the deployment platform?
[4] [2026-03-01 14:06] alice: GCP, it's free tier
[5] [2026-03-01 14:06] bob: ok
```

### System prompt

```
You are analyzing a Discord conversation to identify topical segments
and summarize each one.

SEGMENTATION RULES:
- A segment is a group of consecutive messages about the same topic.
- Short acknowledgments (yes, ok, agreed, thanks) belong to the
  topic they respond to — never a separate segment.
- Topic shifts happen when the conversation moves to a substantially
  different subject.
- Let the conversation determine natural segment sizes. A 2-message
  exchange and a 40-message thread are both valid segments.
- Messages from [BOT] authors are part of the conversation — include
  them in segments with the messages they respond to.

SYNTHESIS RULES:
- For each segment, write a 2-4 sentence summary that captures the
  COMPLETE meaning of the exchange.
- Resolve ALL implicit references: if someone says "yes", state what
  they agreed to. If someone says "that one", state which option.
- Include participant names and any decisions, facts, or commitments.
- The synthesis must be understandable WITHOUT reading the original
  messages.

Return a JSON array of segments, ordered by start_index.
```

### Structured output schema (Gemini response_json_schema)

```json
{
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "start_index": {"type": "integer"},
      "end_index": {"type": "integer"},
      "topic_label": {"type": "string"},
      "synthesis": {"type": "string"}
    },
    "required": ["start_index", "end_index", "topic_label", "synthesis"]
  }
}
```

### Validation

After Gemini returns segments:
- Verify start_index <= end_index for each segment
- Verify segments are ordered and non-overlapping
- Verify all message indices are covered (no gaps)
- If validation fails: retry once, then fall back to time-gap
  segmentation (split on gaps > 30 minutes between messages)
  with raw message concatenation as synthesis

### Batch boundaries

When processing 500-message batches, the last segment in a batch
may span the boundary. Handle by including a 20-message overlap
window — the last 20 messages of batch N are also the first 20
of batch N+1. Segments that start in the overlap zone of the
previous batch are discarded (already captured). Segments that
start before the overlap but extend into it are kept from the
first batch.

### Time-gap fallback segmentation

If LLM segmentation fails entirely:
```python
def fallback_segment(messages, gap_minutes=30):
    """Split on time gaps > gap_minutes. No LLM call."""
    segments = []
    current = [messages[0]]
    for msg in messages[1:]:
        gap = (msg.created_at - current[-1].created_at).minutes
        if gap > gap_minutes:
            segments.append(current)
            current = [msg]
        else:
            current.append(msg)
    if current:
        segments.append(current)
    return segments
```

Synthesis for fallback segments: concatenate messages as
"author: content" with newlines. No LLM resolution of meaning.

---

*Continued in Part 2: Retrieval, Citations, Clustering Changes*
