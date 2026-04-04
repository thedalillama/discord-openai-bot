# SOW v5.6.0 — Context-Prepended Embeddings
# Part 1 of 2: Objective, Design, Embedding Strategy
# Status: PROPOSED — awaiting approval
# Branch: claude-code
# Prerequisite: v5.5.0 (cluster-based retrieval working)

---

## Objective

Change the embedding strategy from individual message embedding to
context-prepended embedding. Before embedding a message, prepend the
previous 3-5 messages as conversational context. When a message has
a `reply_to_message_id`, use the replied-to message as primary context.

This fixes two validated problems:
1. Short replies ("yes", "agreed", "good idea") embed as generic
   affirmations and cluster with other short replies instead of
   with the conversation they belong to
2. Bot responses about different topics cluster together because
   they share similar language patterns — with context prepending,
   each bot response embeds with its unique conversational context

After v5.6.0, all messages get re-embedded and re-clustered with
the new strategy. Existing clusters are rebuilt from scratch.

---

## Research Basis

The embedding research report found:
- No production system embeds short chat messages in isolation
- Amazon/Alexa research: adding prior-turn context improved topic
  classification from 55% to 74% (35% relative improvement)
- Anthropic's Contextual Retrieval: 35% reduction in retrieval
  failure with contextual embeddings
- The fix is ~20 lines of code with negligible cost increase

---

## Design

### Context Construction

For each message being embedded, build a contextual text string:

```python
def build_contextual_text(channel_id, message_id, author, content,
                          reply_to_id=None, window=3):
    """Build context-prepended text for embedding.

    Priority:
    1. If reply_to_id exists, fetch the replied-to message and use
       it as primary context (plus 1-2 messages before the reply)
    2. Otherwise, fetch the previous `window` messages by timestamp

    Returns formatted string for embedding.
    """
```

**Format:**
```
[Context: author1: previous message 1 | author2: previous message 2 | author3: previous message 3]
author4: current message
```

**Example — before:**
```
Embedding: "yes"
→ generic affirmation vector, clusters with other "yes" messages
```

**Example — after:**
```
Embedding: "[Context: absolutebeginner: Should we use PostgreSQL?]
Synthergy-GPT4: yes"
→ database decision vector, clusters with database discussion
```

### Reply Chain Handling

When `reply_to_message_id` is set:
1. Fetch the replied-to message from the `messages` table
2. Also fetch 1-2 messages before the replied-to message for
   additional context
3. Use this as context instead of the chronologically previous
   messages

This handles cases where a reply references a message from 50
messages ago — outside any sliding window but explicitly linked.

```python
if reply_to_id:
    # Fetch replied-to message + 1-2 before it
    context_msgs = get_reply_context(channel_id, reply_to_id, n=2)
else:
    # Fetch previous N messages by timestamp
    context_msgs = get_previous_messages(channel_id, message_id, n=window)
```

### Where This Lives

Add `build_contextual_text()` to a new module or to an existing one.
Options:
- `utils/embedding_store.py` — where `embed_text()` lives
- New `utils/embedding_context.py` — if embedding_store is near 250

The function queries the `messages` table for context, so it needs
SQLite access. Wrap in `asyncio.to_thread()` when called from
`raw_events.py`.

### Changes to Embedding on Arrival (`raw_events.py`)

Currently:
```python
embed_and_store_message(message_id, content)
```

After:
```python
contextual_text = build_contextual_text(
    channel_id, message_id, author, content,
    reply_to_id=reply_to_message_id)
embed_and_store_message(message_id, contextual_text)
```

The `embed_and_store_message()` function itself doesn't change —
it still takes text and returns a vector. The text it receives is
now richer.

### Changes to Backfill (`debug_commands.py`)

`!debug backfill` currently embeds each message's raw content.
Update it to use `build_contextual_text()` for each message.
Since backfill processes messages in chronological order, the
context messages will already be in the table when needed.

### Token Cost Impact

With 3-message context window, token count per embedding increases
roughly 3-5x. At $0.02/1M tokens for text-embedding-3-small:
- Without context: 741 msgs × ~20 tokens = ~15K tokens = $0.0003
- With context: 741 msgs × ~80 tokens = ~59K tokens = $0.0012

Negligible cost difference.

### Query Embedding

When the user sends a message and we embed it for retrieval
(`embed_text()` in `_retrieve_cluster_context`), should we also
prepend context?

**Yes** — the query should be embedded in the same space as the
stored embeddings. Use the same `build_contextual_text()` for the
query message. The context is the recent conversation the user is
participating in, which is already available in `conversation_msgs`.

Update `_retrieve_cluster_context()` in `context_manager.py`:
```python
# Before:
query_vec = embed_text(query_text)

# After:
contextual_query = build_contextual_text(
    channel_id, msg_id, author, query_text,
    reply_to_id=reply_to_id)
query_vec = embed_text(contextual_query)
```

---

*Continued in Part 2: Re-embedding, Re-clustering, Testing*
