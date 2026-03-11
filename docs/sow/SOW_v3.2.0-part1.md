# SOW v3.2.0 — Structured Summary Generation (Roadmap M2)
# Part 1 of 2: Schema, Verification, and Architecture

**Status**: Proposed — awaiting approval
**Branch**: development
**Prerequisite**: v3.1.0 (schema extension, channel_summaries table)
**Roadmap reference**: Phase 2, Milestone 2

## Problem Statement

The bot loses all conversational context beyond the token budget window.
When `build_context_for_provider()` trims older messages, decisions,
preferences, action items, and facts discussed earlier in the conversation
are silently dropped. The bot has no memory of what happened before the
current window.

The v3.1.0 persistence layer stores all raw messages in SQLite, and the
`channel_summaries` table is ready to receive structured summary JSON.
This milestone introduces the summarizer that reads raw messages, produces
a structured JSON summary, and stores it — completing the first half of
the memory system (M3 will inject it into prompts).

## Objectives

1. Define the structured summary JSON schema with drift-resistant
   protections for critical content.
2. Implement a summarizer module that calls a dedicated AI provider to
   produce incremental summary updates from raw messages.
3. Implement hash-based integrity verification for protected fields
   (decisions, key facts, action items).
4. Implement source verification for initial extraction accuracy.
5. Store summaries in the `channel_summaries` table.
6. Add `!summarize` command for manual trigger.
7. Add `!summary` command to view the current summary.
8. Target: summary JSON stays under 2,000 tokens.

## Design

### Summary JSON Schema (v1.0)

```json
{
  "schema_version": "1.0",
  "channel_id": "string",
  "updated_at": "ISO-8601",
  "summary_token_count": 0,
  "participants": [
    {
      "id": "discord_user_id",
      "display_name": "string",
      "first_seen": "ISO-8601"
    }
  ],
  "overview": "1-3 sentence summary of the channel's purpose and recent activity",
  "active_topics": [
    { "id": "topic-001", "title": "Short descriptive title",
      "status": "discussed|decided|active|completed|archived",
      "summary": "Concise narrative", "participants": ["discord_user_id"],
      "first_raised": "ISO-8601", "last_updated": "ISO-8601",
      "source_message_ids": [1234, 1238] }
  ],
  "decisions": [
    {
      "id": "dec-001",
      "decision": "Exact wording of what was decided",
      "decision_hash": "a7f3b2c8",
      "context": "Brief rationale — compressible",
      "made_by": ["discord_user_id"],
      "date": "ISO-8601",
      "status": "active|amended|superseded|rescinded",
      "supersedes": null,
      "source_message_ids": [1234, 1238]
    }
  ],
  "key_facts": [
    {
      "id": "fact-001",
      "fact": "Verbatim or near-verbatim critical statement",
      "fact_hash": "c4e8a1d9",
      "category": "metric|commitment|requirement|constraint|reference",
      "pinned": true,
      "source": "discord_user_id",
      "date": "ISO-8601",
      "source_message_ids": [5678],
      "source_verified": null
    }
  ],
  "action_items": [
    {
      "id": "act-001",
      "task": "Verb-first description of specific task",
      "task_hash": "e2b7f4a1",
      "owner": "discord_user_id|null",
      "deadline": "ISO-8601|null",
      "status": "open|in_progress|completed|deferred|cancelled",
      "source_message_ids": [5680]
    }
  ],
  "open_questions": [
    { "id": "q-001", "question": "What needs to be resolved?",
      "status": "open|answered|deferred", "raised_by": "discord_user_id",
      "date": "ISO-8601", "answer": null, "source_message_ids": [4200] }
  ],
  "pinned_memory": [
    {
      "id": "pin-001",
      "text": "Critical statement that must never be compressed",
      "text_hash": "f1a9c3e7",
      "source_message_ids": [4500, 4502],
      "source_verified": null
    }
  ],
  "meta": {
    "model": "provider/model-name",
    "summarized_at": "ISO-8601",
    "token_count": 0,
    "message_range": {
      "first_id": 0,
      "last_id": 0,
      "count": 0
    },
    "verification": {
      "protected_items_count": 0,
      "hashes_verified": 0,
      "mismatches": 0,
      "source_checks_passed": 0,
      "source_checks_failed": 0
    }
  }
}
```

### Protected Fields and Hash Verification

The following fields are hashed at creation time using SHA-256
truncated to 8 hex characters:

| Item Type | Protected Field | Hash Field | Compressible Fields |
|-----------|----------------|------------|---------------------|
| Decision | `decision` | `decision_hash` | `context` |
| Key Fact | `fact` | `fact_hash` | (none) |
| Action Item | `task` | `task_hash` | (none) |
| Pinned Memory | `text` | `text_hash` | (none) |

**Lifecycle rules for protected items:**

- **ADD**: Create new item, compute hash from content, store both.
- **SUPERSEDE** (decisions only): Set old item status to `superseded`,
  create new item with `supersedes` back-reference and new hash.
- **COMPLETE/CLOSE**: Change `status` only. Content and hash untouched.
- **MODIFY content**: **Prohibited.** The verification layer rejects
  any update where the hash no longer matches the content.

After every summarization cycle, the verification layer:

1. Before applying updates, reads the current summary JSON from the
   database as the pre-update snapshot.
2. Applies the LLM's incremental updates to produce the candidate summary.
3. Iterates all items with hash fields in the candidate.
4. Recomputes hash from current content.
5. If mismatch on any item: restores that specific item's protected
   field from the pre-update snapshot. Other valid updates are kept.
   Logs a warning per mismatch.
6. Records results in `meta.verification`.

### Source Verification for Initial Extraction

When the summarizer creates a new pinned item (category: `metric`,
`reference`, `constraint`, or `commitment`), the verification layer
checks whether the protected content appears verbatim in the source
messages referenced by `source_message_ids`.

Process:

1. Retrieve source messages from SQLite by their IDs.
2. Search for the exact `fact`, `decision`, or `task` string within
   the concatenated source message content.
3. If found: set `"source_verified": true` on the item.
4. If not found: set `"source_verified": false` on the item. The item
   is still stored but marked for review.

This catches hallucinated or paraphrased extractions at creation time.
It does not apply to synthesized content like topic summaries or
decision context, which are inherently paraphrased.

### Summarizer Provider Configuration

New environment variables in `config.py`:

```
SUMMARIZER_PROVIDER=deepseek        # Provider for summarization calls
SUMMARIZER_MODEL=deepseek-chat      # Model for summarization calls
```

The summarizer instantiates its own provider instance via the existing
`get_provider()` factory using `SUMMARIZER_PROVIDER`. This is independent
of per-channel conversation providers. If `SUMMARIZER_PROVIDER` is not
set, falls back to the global `AI_PROVIDER` default.

The summarizer uses `temperature=0` (or near-zero) for all calls to
minimize non-deterministic drift per the research recommendation.

### Summarizer Module Architecture

New file: `utils/summarizer.py`

Responsibilities:

1. Read current summary from `channel_summaries` table (or initialize
   empty schema if none exists).
2. Read unsummarized messages from SQLite — messages with IDs after
   `channel_summaries.last_message_id` for the channel.
3. Build a summarization prompt containing:
   - The current summary JSON
   - The new messages formatted with short labels (M1, M2, M3...)
   - Explicit instructions for incremental updates only
   - Rules for protected fields and lifecycle operations
   - Promotion rules (what gets promoted vs. filtered)
4. Call the summarizer provider via `loop.run_in_executor()` with
   `ThreadPoolExecutor` (matching the established provider call pattern
   in CLAUDE.md — `asyncio.to_thread()` is only used for SQLite
   operations in `raw_events.py`).
5. Parse the LLM response as JSON.
6. Run hash verification on all protected fields.
7. Run source verification on new pinned items.
8. Compute hashes for any new protected items.
9. Store the updated summary in `channel_summaries`.
10. Log verification results.

**Promotion rules** (what gets promoted to structured memory):

- Explicit decisions
- User preferences and stated constraints
- Commitments with owners or deadlines
- Recurring facts and important context
- Open questions awaiting resolution
- Active tasks and action items
- Filenames, paths, URLs, version numbers, config values

**Non-promotable content** (filtered out):

- Casual filler and greetings
- One-off acknowledgments
- Jokes that don't become recurring context
- Low-value small talk

*Continued in Part 2: Prompt Design, Commands, and Implementation Plan*
