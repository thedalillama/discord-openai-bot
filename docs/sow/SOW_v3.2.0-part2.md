# SOW v3.2.0 — Structured Summary Generation (Roadmap M2)
# Part 2 of 2: Prompt Design, Commands, and Implementation Plan

*Continued from Part 1: Schema, Verification, and Architecture*

### Summarizer Prompt Design

The prompt instructs the LLM to return a JSON object containing only
the incremental updates, not the full summary. This is the Chain-of-Key
approach — targeted updates on specific fields rather than full
regeneration.

The prompt includes:

```
You are a conversation summarizer. You receive a current summary JSON
and a batch of new messages. Return ONLY a JSON object with the
changes to apply.

RULES:
- Return incremental updates only: ADD, SUPERSEDE, CLOSE, or UPDATE
  operations on specific items.
- Never modify the protected field of any existing decision, key_fact,
  action_item, or pinned_memory item.
- To change a decision, SUPERSEDE it: set old status to "superseded"
  and create a new decision with a "supersedes" back-reference.
- Preserve filenames, paths, URLs, version numbers, and numerical
  values exactly as they appear in the source messages.
- Use source_message_ids to reference the message labels (M1, M2...)
  provided in the context.
- Only promote durable information. Skip casual filler.
- Keep the overview to 1-3 sentences.
- Temperature is 0. Be precise, not creative.
```

The response format:

```json
{
  "overview_update": "Updated overview text or null if unchanged",
  "new_participants": [...],
  "topic_updates": [
    {"action": "add|update|close", "item": {...}}
  ],
  "decision_updates": [
    {"action": "add|supersede", "item": {...}}
  ],
  "fact_updates": [
    {"action": "add", "item": {...}}
  ],
  "action_item_updates": [
    {"action": "add|complete|close", "item": {...}}
  ],
  "question_updates": [
    {"action": "add|answer|close", "item": {...}}
  ],
  "pinned_memory_updates": [
    {"action": "add", "item": {...}}
  ]
}
```

The Python code applies these updates to the existing summary, computes
hashes for new items, verifies hashes on existing items, and stores
the result.

### Duplicate Item ID Handling

When applying incremental updates, if the LLM returns an ADD operation
for an item ID that already exists in the current summary, the update
is rejected and logged as a warning. The existing item is preserved
unchanged.

If the LLM intended to modify an existing item, it must use the
appropriate lifecycle operation (UPDATE, SUPERSEDE, COMPLETE, CLOSE) —
not ADD. Rejecting duplicate ADDs catches a class of LLM errors where
it re-extracts content already present in the summary.

This check runs before hash verification, during the update application
step.

### Message Labeling

When building the summarizer prompt, messages from SQLite are labeled
with short sequential IDs:

```
[M1] Alice (2026-03-10 14:30): We should use SQLite for this.
[M2] Bob (2026-03-10 14:32): Agreed, Redis is overkill.
[M3] Alice (2026-03-10 14:35): I'll write the schema tonight.
```

The label-to-message-ID mapping is maintained so that `source_message_ids`
in the summary can reference the actual Discord snowflake IDs, not the
short labels. The LLM sees M1/M2/M3; the stored summary uses real IDs.

### !summarize Command

New command in `commands/summary_commands.py`:

```
!summarize          — Run summarization for this channel (admin only)
```

Workflow:

1. Check admin permissions.
2. Show typing indicator.
3. Call `summarize_channel(channel_id)` from `utils/summarizer.py`.
4. Report result: number of messages processed, verification results,
   token count of the summary.

### !summary Command

```
!summary            — Show current channel summary (all users)
```

Workflow:

1. Read summary from `channel_summaries` table.
2. If none exists, report "No summary available. An admin can run
   !summarize to generate one."
3. Format key sections for Discord display: overview, active topics,
   recent decisions, open action items, open questions.
4. Truncate for Discord's 2000-char limit if needed.

### Summary Storage

The `channel_summaries` table (created in v3.1.0) stores:

- `channel_id` (PK): Discord channel ID
- `summary_json`: Full JSON summary string
- `updated_at`: ISO 8601 timestamp
- `message_count`: Number of messages summarized
- `last_message_id`: Snowflake ID of the last message included

New functions in `message_store.py`:

```python
def save_channel_summary(channel_id, summary_json, message_count, last_message_id):
    """Insert or update the summary for a channel."""

def get_channel_summary(channel_id):
    """Return the summary JSON string for a channel, or None."""
```

## New Files

| File | Version | Description |
|------|---------|-------------|
| `utils/summarizer.py` | v1.0.0 | Summarization engine: prompt building, LLM call, update application, verification |
| `utils/summary_schema.py` | v1.0.0 | Schema definition, empty summary factory, hash utilities, verification functions |
| `commands/summary_commands.py` | v1.0.0 | !summarize and !summary commands |
| `docs/sow/SOW_v3.2.0.md` | — | This document (both parts) |

No new schema migration file — the `channel_summaries` table already
exists from `schema/002.sql` (v3.1.0). The next `schema/NNN.sql` file
is reserved for whichever future milestone needs schema changes.

## Modified Files

| File | Old Version | New Version | Changes |
|------|------------|-------------|---------|
| `utils/message_store.py` | v1.1.0 | v1.2.0 | Add save_channel_summary(), get_channel_summary() |
| `config.py` | v1.7.0 | v1.8.0 | Add SUMMARIZER_PROVIDER, SUMMARIZER_MODEL env vars |
| `commands/__init__.py` | current | +1 | Import and register summary_commands |
| `STATUS.md` | v3.1.0 | v3.2.0 | Version history |
| `HANDOFF.md` | v3.1.0 | v3.2.0 | Current state |

## Unchanged Files

bot.py, raw_events.py, models.py, db_migration.py, context_manager.py,
response_handler.py, all existing providers, all existing commands,
and the entire `utils/history/` subsystem. The in-memory response
pipeline is untouched — M3 wires the summary into prompts.

## Risk Assessment

**Medium.** This is the first milestone that calls an LLM for a purpose
other than user-facing responses. Risks and mitigations:

- **LLM returns invalid JSON**: Parse in try/except, log error, skip
  update. The previous summary remains intact in the database.
- **LLM modifies protected content**: Hash verification detects and
  rejects the modification, restoring from pre-update snapshot.
- **LLM hallucinate facts**: Source verification flags items where
  the extracted text doesn't appear in source messages.
- **Summary exceeds 2,000 token target**: Log warning, but do not
  truncate. The token budget in M3 will handle allocation.
- **Summarizer provider unavailable**: Error logged, summary unchanged.
  The bot continues operating normally without summarization.
- **Cost**: Manual-only trigger means no runaway costs. Each call
  processes only unsummarized messages, not the full history.

## Testing

1. **First summarize**: Run `!summarize` in a channel with 50+ messages.
   Verify summary JSON is valid, stored in `channel_summaries`, and
   contains participants, topics, and any decisions from the conversation.
2. **Incremental update**: Send 10 more messages including a decision.
   Run `!summarize` again. Verify only new messages were processed and
   the decision appears in the summary.
3. **Hash verification**: Manually edit a decision's `decision` field
   in the database. Run `!summarize`. Verify the verification layer
   detects the mismatch and restores the original.
4. **Source verification**: Check that pinned facts with category
   `reference` or `metric` have `source_verified` flags.
5. **Supersession**: Make a decision, summarize. Change the decision
   in conversation, summarize again. Verify the old decision is
   `superseded` and the new one has a `supersedes` back-reference.
6. **!summary display**: Run `!summary`. Verify readable output
   showing overview, topics, decisions, action items.
7. **Empty channel**: Run `!summarize` on a channel with no messages.
   Verify graceful handling.
8. **Provider failure**: Set `SUMMARIZER_PROVIDER` to an invalid value.
   Run `!summarize`. Verify error is caught and reported cleanly.
9. **Token count**: Verify `meta.token_count` is populated and the
   summary stays near the 2,000 token target.
10. **No regression**: Address the bot normally, verify responses are
    unaffected (summary is not yet injected into prompts — that's M3).
