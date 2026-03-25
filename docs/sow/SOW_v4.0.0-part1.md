# SOW v4.0.0 — Topic-Based Semantic Retrieval
# Part 1 of 2: Problem, Design, Schema, Write Path

**Status**: Proposed — awaiting approval
**Branch**: claude-code
**Prerequisite**: v3.5.x (unified three-pass pipeline, classifier dedup)
**Replaces**: Original M4 Episode Segmentation design

## Problem Statement

The bot injects the full channel summary into every response. As the
channel grows, most of the summary is irrelevant to any given question.
When a user asks about databases, the context includes bachelor party
toasts, animal evolution facts, and gardening tips. This dilutes the
signal and wastes token budget.

Meanwhile, genuinely relevant context from older messages sits outside
the recent message window entirely. The user discussed PostgreSQL
hosting details 400 messages ago — those raw messages contain nuance
that the one-line decision summary doesn't capture.

The original M4 (Episode Segmentation) addressed summary size through
time-slicing but did not address relevance. The classifier already
controls summary growth (v3.5.1). The actual problem is **retrieving
the right context for the right question**.

## Objectives

1. Store topics as first-class entities in SQLite with embeddings.
2. Store message embeddings at write time (one API call, cached forever).
3. Link topics to their source messages via embedding similarity.
4. On each bot response, embed the incoming message, find the most
   relevant topics by cosine similarity, and pull their linked messages
   into the context window.
5. Replace full summary injection with a slim "always-on" context
   (overview + open action items + open questions) plus retrieved
   topic messages.
6. Provide a backfill mechanism for existing messages and topics.

## Design

### Embedding Provider

Gemini `text-embedding-004` via the existing `google-genai` SDK.
Free tier, no additional API keys needed. The `GEMINI_API_KEY`
already in `.env` covers embedding calls.

```python
from google import genai

client = genai.Client(api_key=GEMINI_API_KEY)
result = client.models.embed_content(
    model="text-embedding-004",
    content="text to embed",
)
vector = result.embedding  # list of floats
```

Embedding dimension: 768 floats = ~3KB per vector as BLOB.

### New Database Tables

New migration file: `schema/004.sql`

```sql
-- schema/004.sql
-- v4.0.0: Topic-based semantic retrieval

-- Topics as first-class entities
CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    status TEXT DEFAULT 'active',
    embedding BLOB,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_topics_channel
    ON topics(channel_id, status);

-- Junction: which messages belong to which topic
CREATE TABLE IF NOT EXISTS topic_messages (
    topic_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    PRIMARY KEY (topic_id, message_id),
    FOREIGN KEY (topic_id) REFERENCES topics(id),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);
CREATE INDEX IF NOT EXISTS idx_topic_messages_message
    ON topic_messages(message_id);

-- Message embeddings (one per message, computed once)
CREATE TABLE IF NOT EXISTS message_embeddings (
    message_id INTEGER PRIMARY KEY,
    embedding BLOB NOT NULL,
    FOREIGN KEY (message_id) REFERENCES messages(id)
);
```

Separate `message_embeddings` table keeps the messages table lean
for queries that don't need embeddings.

### Embedding Storage Format

Vectors stored as BLOB using Python `struct.pack`:

```python
import struct

def pack_embedding(vector):
    """Pack list of floats to bytes for SQLite BLOB."""
    return struct.pack(f'{len(vector)}f', *vector)

def unpack_embedding(blob):
    """Unpack bytes BLOB to list of floats."""
    n = len(blob) // 4
    return list(struct.unpack(f'{n}f', blob))
```

768 floats × 4 bytes = 3,072 bytes per embedding.
540 messages × 3KB = ~1.6 MB total. Negligible.

### Cosine Similarity

Pure Python, no dependencies:

```python
import math

def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
```

For ~20 topics, this takes microseconds.

### New Module: `utils/embedding_store.py`

Handles all embedding operations:

- `embed_text(text)` — calls Gemini embedding API, returns float list
- `store_message_embedding(message_id, embedding)` — writes BLOB
- `store_topic(channel_id, topic_id, title, summary, status)` —
  INSERT OR REPLACE into topics table
- `store_topic_embedding(topic_id, embedding)` — UPDATE on topics
- `link_topic_to_messages(topic_id, channel_id, top_n=20)` —
  embed topic, compare against all message embeddings in channel,
  write top-N matches to topic_messages
- `get_topic_embeddings(channel_id)` — returns (id, title, embedding)
- `embed_and_store_message(message_id, text)` — embed + store
- `pack_embedding()` / `unpack_embedding()` — BLOB serialization
- `cosine_similarity(a, b)` — vector comparison
- `find_relevant_topics(query_embedding, channel_id, top_k=5)` —
  loads topic embeddings, computes similarity, returns top K

All database operations designed for `asyncio.to_thread()` wrapping.
Embedding API calls use `run_in_executor()` per AGENT.md async rules.

### Topic-Message Linkage via Embedding Similarity

**Important**: The Structurer does NOT reliably populate
`source_message_ids` on topics. The Secretary writes natural language
minutes without M-labels, and the Structurer works from those minutes,
so it has no message IDs to cite on topic ops. (It does cite them on
decisions, facts, and action items — those remain for audit trail.)

Instead, `topic_messages` is populated by **embedding similarity**:

1. When a topic is stored, embed its title + summary text
2. Load all message embeddings for the channel
3. Compute cosine similarity between the topic and each message
4. Take the top-N most similar messages (default N=20)
5. Write those pairs to `topic_messages`

This is more robust than Structurer citation because:
- It catches related messages the Structurer didn't explicitly cite
- It works for topics where the Secretary condensed many messages
- It uses the same embedding infrastructure already being built

### Write Path: Message Embedding on Arrival

In `raw_events.py`, after storing a message in
`persistence_on_message()`, compute and store its embedding:

```python
# After insert_message(stored_msg):
try:
    from utils.embedding_store import embed_and_store_message
    await asyncio.to_thread(
        embed_and_store_message, stored_msg.id, stored_msg.content
    )
except Exception as e:
    logger.warning(f"Embedding failed for {stored_msg.id}: {e}")
```

**Fail-safe**: If embedding fails, the message is still stored.
Embedding can be backfilled later.

**Skip noise**: Do not embed messages starting with `!`, or
identified as noise (`ℹ️`) or settings (`⚙️`) messages.

### Write Path: Topic Storage After Pipeline

In `summarizer_authoring.py`, after `apply_ops()` and
`save_channel_summary()`, write topics to SQLite and link them
to messages by embedding similarity:

```python
from utils.embedding_store import store_topic, link_topic_to_messages
for topic in updated.get("active_topics", []):
    await asyncio.to_thread(
        store_topic, channel_id, topic["id"],
        topic["title"], topic.get("summary", ""),
        topic.get("status", "active"))
    await asyncio.to_thread(
        link_topic_to_messages, topic["id"], channel_id)
```

`link_topic_to_messages()` embeds the topic, compares against all
message embeddings in the channel, and writes the top-N matches to
`topic_messages`. This runs after every summarization — as new
messages arrive and get embedded, topics pick up new related messages.

### Backfill

**Message embeddings**: A `!debug backfill_embeddings` command queries
all messages without embeddings, filters noise, batch-embeds via
Gemini API, and stores results. For 540 messages: a few API calls,
free tier.

**Topic backfill**: `!summary clear` + `!summary create` populates
the topics table and computes embeddings + linkages from scratch.
Alternatively, a backfill script reads the existing summary JSON
and populates `topics` + embeddings without re-running the full
summarizer.
