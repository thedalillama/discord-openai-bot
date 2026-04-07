# SOW v5.7.0 — Explainability & Context Receipts
# Part 1 of 2: Receipt Capture, Storage, Architecture
# Status: PROPOSED — awaiting approval
# Branch: claude-code
# Prerequisite: v5.6.1 (context-prepended embeddings + smart query)

---

## Objective

For every bot response, store a context receipt that records exactly
what information was assembled into the prompt. Add a `!explain`
command that displays the receipt for the most recent bot response.

This is strictly what-was-included reporting, never claims about
hidden reasoning. The receipt is a permanent record that can be
inspected at any time, not a post-hoc reconstruction.

---

## Existing Infrastructure

The `response_context_receipts` table already exists (schema 002.sql):

```sql
response_context_receipts (
    response_message_id INTEGER PRIMARY KEY,
    user_message_id INTEGER,
    channel_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    receipt_json TEXT NOT NULL
)
```

This table is empty — it was created in anticipation of M5 but
never populated. No schema changes needed.

---

## Receipt Capture: Where and What

### Where to Capture

The receipt must be captured after context assembly but linked to
the bot's response message. The call flow is:

```
bot.py on_message()
  → build_context_for_provider(channel_id, provider)
      → format_always_on_context(summary)     ← capture this
      → _retrieve_cluster_context(...)         ← capture this
      → select recent messages                 ← capture this
  → handle_ai_response(message, channel_id, messages)
      → generate_ai_response(...)
      → send response to Discord               ← get response msg ID
      → store receipt with response msg ID
```

Two options for implementation:

**Option A**: `build_context_for_provider()` returns the receipt
data alongside the message list. `handle_ai_response()` stores the
receipt after sending the response (so it has the response message ID).

**Option B**: `build_context_for_provider()` stores receipt data in
a module-level dict keyed by channel_id. After `handle_ai_response()`
sends the response, it reads the receipt and stores it with the
response message ID.

**Recommend Option A** — explicit data flow, no shared mutable state.
Change `build_context_for_provider()` to return a tuple:
`(messages, receipt_data)` where `receipt_data` is a dict or None.

### What to Capture

The receipt_json should contain:

```json
{
    "query": "how strong are squirrels?",
    "query_embedding_path": "raw" | "question_context" | "similarity_context",
    "always_on": {
        "overview_tokens": 50,
        "key_facts_count": 8,
        "decisions_count": 5,
        "action_items_count": 3,
        "open_questions_count": 0,
        "total_tokens": 278
    },
    "retrieved_clusters": [
        {
            "cluster_id": "cluster-...-15",
            "label": "Squirrel Strength Discussion",
            "score": 0.846,
            "messages_injected": 12,
            "tokens": 557
        },
        {
            "cluster_id": "cluster-...-8",
            "label": "Animal Strength Comparison",
            "score": 0.742,
            "messages_injected": 25,
            "tokens": 3006
        }
    ],
    "clusters_below_threshold": [
        {"label": "Bot Availability Check", "score": 0.21}
    ],
    "fallback_used": false,
    "fallback_messages": 0,
    "recent_messages": 5,
    "total_context_tokens": 4168,
    "budget_tokens": 12000,
    "budget_used_pct": 34.7,
    "provider": "deepseek",
    "model": "deepseek-reasoner"
}
```

### Collecting Receipt Data

The data is already computed during context assembly — it just
needs to be collected instead of only logged:

**In `_retrieve_cluster_context()`**: Already computes cluster IDs,
labels, scores, message counts, and token counts. Build a list of
cluster dicts and return it alongside the context text.

**In `build_context_for_provider()`**: Already computes always-on
tokens, retrieval tokens, recent message count, total budget.
Assemble the receipt dict from these values.

**In `embed_query_with_smart_context()`**: Already logs which path
was taken (question context, similarity context, raw). Return the
path name alongside the vector.

---

## Receipt Storage

### New Module: `utils/receipt_store.py`

```python
def save_receipt(response_message_id, user_message_id,
                 channel_id, receipt_dict):
    """Store a context receipt for a bot response."""

def get_latest_receipt(channel_id):
    """Get the most recent receipt for a channel.
    Returns (response_message_id, receipt_dict) or (None, None).
    """

def get_receipt_by_response(response_message_id):
    """Get receipt for a specific bot response.
    Returns receipt_dict or None.
    """
```

### When to Store

In `handle_ai_response()` in `response_handler.py` (or `bot.py`
depending on where the response is sent), after the bot's response
message is sent to Discord:

```python
# After sending response and getting the response message:
if receipt_data:
    await asyncio.to_thread(
        save_receipt,
        response_msg.id,
        message.id,
        channel_id,
        receipt_data
    )
```

### Fail-Safe

Receipt storage must never prevent the bot from responding. Wrap
in try/except — if storage fails, log a warning and continue.

---

*Continued in Part 2: !explain Command, Display, Testing*
