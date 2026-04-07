# SOW v5.7.0 — Explainability & Context Receipts
# Part 2 of 2: !explain Command, Display, Testing
# Status: PROPOSED — awaiting approval
# Branch: claude-code

---

## The `!explain` Command

### Basic Usage

```
!explain
```

Shows the context receipt for the bot's most recent response in the
channel. Output format:

```
ℹ️ **Context Receipt** (response to: "how strong are squirrels?")

**Query Embedding**: raw (no context prepended)

**Always-On Context** (278 tokens):
  Overview: ✓
  Key facts: 8 items
  Decisions: 5 items
  Action items: 3 items

**Retrieved Clusters** (3,563 tokens):
  1. Squirrel Strength Discussion — score 0.846, 12 msgs (557 tok)
  2. Animal Strength Comparison — score 0.742, 25 msgs (3,006 tok)

**Below Threshold** (filtered out):
  Bot Availability Check — score 0.21

**Recent Messages**: 5

**Budget**: 4,168 / 12,000 tokens (34.7%)
**Provider**: deepseek / deepseek-reasoner
```

### Optional: Explain a Specific Response

```
!explain <message_id>
```

Looks up the receipt for a specific bot response by its Discord
message ID. If not found, shows an error.

### Edge Cases

- `!explain` when no receipts exist: "No context receipts found.
  Receipts are stored starting from this version."
- `!explain` when the last response had no receipt (e.g., error
  response): "No receipt available for the last response."
- `!explain <invalid_id>`: "No receipt found for that message."

---

## Display Formatting

Add display logic to a new command file or to the existing
`commands/debug_commands.py`. The formatting should be concise
and readable in Discord.

```python
def format_receipt(receipt, query_text=None):
    """Format a receipt dict for Discord display."""
    lines = []

    if query_text:
        lines.append(f'**Context Receipt** (response to: "{query_text[:80]}")')
    else:
        lines.append("**Context Receipt**")

    # Query embedding path
    path = receipt.get("query_embedding_path", "unknown")
    lines.append(f"\n**Query Embedding**: {path}")

    # Always-on
    ao = receipt.get("always_on", {})
    lines.append(f"\n**Always-On Context** ({ao.get('total_tokens', 0)} tokens):")
    lines.append(f"  Overview: {'✓' if ao.get('overview_tokens', 0) > 0 else '✗'}")
    lines.append(f"  Key facts: {ao.get('key_facts_count', 0)} items")
    lines.append(f"  Decisions: {ao.get('decisions_count', 0)} items")
    lines.append(f"  Action items: {ao.get('action_items_count', 0)} items")

    # Retrieved clusters
    clusters = receipt.get("retrieved_clusters", [])
    total_ret = sum(c.get("tokens", 0) for c in clusters)
    lines.append(f"\n**Retrieved Clusters** ({total_ret} tokens):")
    for i, c in enumerate(clusters, 1):
        lines.append(
            f"  {i}. {c['label']} — score {c['score']:.3f}, "
            f"{c['messages_injected']} msgs ({c['tokens']} tok)")

    if not clusters:
        lines.append("  (none — fallback used)")

    # Below threshold
    below = receipt.get("clusters_below_threshold", [])
    if below:
        lines.append(f"\n**Below Threshold** (filtered out):")
        for c in below[:5]:  # show max 5
            lines.append(f"  {c['label']} — score {c['score']:.3f}")

    # Fallback
    if receipt.get("fallback_used"):
        lines.append(
            f"\n**Fallback**: {receipt.get('fallback_messages', 0)} "
            f"msgs retrieved by direct similarity")

    # Recent + budget
    lines.append(f"\n**Recent Messages**: {receipt.get('recent_messages', 0)}")
    total = receipt.get("total_context_tokens", 0)
    budget = receipt.get("budget_tokens", 0)
    pct = receipt.get("budget_used_pct", 0)
    lines.append(f"**Budget**: {total} / {budget} tokens ({pct:.1f}%)")

    # Provider
    provider = receipt.get("provider", "?")
    model = receipt.get("model", "?")
    lines.append(f"**Provider**: {provider} / {model}")

    return lines
```

Use `send_paginated()` for output in case it exceeds 2000 chars.
All output prefixed with ℹ️.

---

## Changes to `build_context_for_provider()`

This is the most significant code change. The function currently
returns `[system_msg] + selected` (a list of messages). It needs
to also return receipt data.

**Option A (recommended)**: Return a tuple `(messages, receipt)`.
Update all callers (there should be one — `bot.py`).

**Option B**: Store receipt in a module-level dict, retrieve later.
Simpler but less clean.

With Option A, `bot.py` changes from:
```python
messages = build_context_for_provider(channel_id, provider)
await handle_ai_response(message, channel_id, messages)
```

To:
```python
messages, receipt = build_context_for_provider(channel_id, provider)
await handle_ai_response(message, channel_id, messages,
                          receipt_data=receipt)
```

The `_retrieve_cluster_context()` function also needs to return
receipt data alongside the context text. Change its return from
`(context_text, tokens_used)` to
`(context_text, tokens_used, cluster_receipt)`.

---

## Testing Plan

### Test 1: Receipt Storage
Send a message to the bot. Then check the database:
```sql
SELECT response_message_id, user_message_id,
       substr(receipt_json, 1, 200)
FROM response_context_receipts
ORDER BY created_at DESC LIMIT 1;
```

### Test 2: `!explain` Basic
Send a message to the bot, then run `!explain`. Verify the output
shows correct clusters, scores, token counts, and provider info.

### Test 3: Different Query Types
- Ask a factual question → `!explain` shows retrieved clusters
- Ask about something never discussed → `!explain` shows fallback
- Send a short reply after a bot question → `!explain` shows
  question_context embedding path

### Test 4: `!explain <message_id>`
Copy a bot response message ID, run `!explain <id>`. Should show
the receipt for that specific response.

### Test 5: No Receipt
Run `!explain` before any new messages are sent (no receipts in
table). Should show a helpful message, not an error.

### Test 6: Fail-Safe
If receipt storage fails (simulate by temporarily corrupting the
table), the bot should still respond normally. Receipt storage
must never block responses.

### Test 7: Existing Functionality
All existing commands still work. Bot responses are not slower
(receipt storage is async, after the response is sent).

---

## Files Changed Summary

| File | Change |
|------|--------|
| NEW `utils/receipt_store.py` | save_receipt(), get_latest_receipt(), get_receipt_by_response() |
| NEW or update `commands/explain_commands.py` | !explain command + display formatting |
| `utils/context_manager.py` or `utils/context_retrieval.py` | Return receipt data from build_context_for_provider() and _retrieve_cluster_context() |
| `bot.py` | Pass receipt data to handle_ai_response(), store after response sent |
| `utils/response_handler.py` | Accept receipt_data param, store after send |

---

## Documentation Updates

- `STATUS.md` — add v5.7.0 entry
- `HANDOFF.md` — update with explainability feature
- `README.md` — add !explain to commands section
- `AGENT.md` — update architecture context

---

## Constraints

1. Full files only
2. Increment version numbers
3. 250-line limit per file
4. ℹ️ prefix on all !explain output
5. Receipt storage must NEVER block or prevent bot responses
6. Receipts are what-was-included, never claims about reasoning
7. asyncio.to_thread() for all SQLite operations
8. All development on claude-code branch
