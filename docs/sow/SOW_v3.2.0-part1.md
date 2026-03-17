# SOW v3.2.0 — Structured Summary Generation (Roadmap M2)
# Part 1 of 2: Schema, Structured Output Enforcement, and Architecture

**Status**: Proposed — awaiting approval
**Branch**: development
**Prerequisite**: v3.1.0 (schema extension, channel_summaries table)
**Roadmap reference**: Phase 2, Milestone 2
**Key reference**: `Forced_JSON_deep-research-report.md` — provides
the delta schema, system instruction, normalization algorithm, and
domain validation patterns used throughout this SOW.

## Problem Statement

The bot loses all conversational context beyond the token budget window.
When `build_context_for_provider()` trims older messages, decisions,
preferences, action items, and facts are silently dropped.

The v3.1.0 persistence layer stores all raw messages in SQLite, and the
`channel_summaries` table is ready to receive structured summary JSON.
This milestone introduces the summarizer that reads raw messages, produces
structured delta operations, applies them to a persistent summary, and
stores the result.

## Why Gemini + Structured Outputs

The first `!summarize` processes the entire message history — 3,200+
messages currently, up to 10,000 from backfill. At ~50 tokens per
message, that's 160K–500K input tokens. DeepSeek's 64K window cannot
fit this without recursive chunking (the drift-prone pattern the
research warns against). Gemini 2.5 Flash Lite's 1M context handles
the full history in a single pass.

Testing revealed that prompt-only JSON instructions are insufficient:
Gemini returns full summary schemas instead of deltas, renames fields,
and exceeds output token limits as summaries grow. The Forced JSON
research report identifies the solution: **API-level structured output
enforcement** using Gemini's `response_mime_type: 'application/json'`
+ `response_json_schema` with a **delta-only schema** that structurally
cannot represent a full summary.

## Objectives

1. Add Gemini as a new AI provider with structured output support.
2. Define a delta-only JSON schema enforced at the Gemini API level.
3. Define the persistent summary schema stored in `channel_summaries`.
4. Implement the three-layer enforcement architecture: hard structural
   constraint, normalization fallback, and domain validation.
5. Implement hash-based integrity verification for protected fields.
6. Implement source verification for initial extraction accuracy.
7. Add `!summarize` and `!summary` commands.
8. Target: summary JSON stays under 2,000 tokens.

## Design

### Gemini Provider

New file: `ai_providers/gemini_provider.py`

Extends `AIProvider` base class. Uses `google-genai` SDK (pip package:
`google-genai`, import: `from google import genai`).

```python
class GeminiProvider(AIProvider):
    self.name = "gemini"
    self.max_context_length = GEMINI_CONTEXT_LENGTH   # default 1,000,000
    self.max_response_tokens = GEMINI_MAX_TOKENS      # default 8,192
    self.supports_images = False
```

The provider supports Gemini Structured Outputs via
`response_mime_type` and `response_json_schema` parameters in the
generation config. The summarizer passes these when calling
`generate_ai_response()`.

Uses `loop.run_in_executor()` with `ThreadPoolExecutor` for the API
call. After success, extracts usage and calls `record_usage()`.

Config variables:

```
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_CONTEXT_LENGTH=1000000
GEMINI_MAX_TOKENS=8192
SUMMARIZER_PROVIDER=gemini
```

### Three-Layer Enforcement Architecture

Per the Forced JSON report, robust structured output requires three
layers. Prompt engineering alone is not sufficient.

**Layer 1 — Hard structural constraint (Gemini Structured Outputs):**
The Gemini API call includes `response_mime_type: 'application/json'`
and `response_json_schema` set to the delta-only schema. Gemini's
constrained decoding enforces that the output matches the schema at
the token generation level. A full summary response is structurally
impossible because the schema only permits the delta format.

**Layer 2 — Normalization fallback:**
If for any reason the structured output constraint fails (edge cases,
SDK version differences, model changes), detect whether the response
is a full summary or a delta. If full summary: canonicalize field
names (`name` → `title`, `source_message_id` → `source_message_ids`)
and run a domain-aware diff against the pre-update snapshot to extract
delta ops. Feed those ops through the normal validation pipeline.

**Layer 3 — Domain validation:**
After either path produces delta ops, validate:
- All `source_message_ids` reference labels present in the context
- No protected-field rewrites (except via supersession)
- No duplicate item IDs on ADD operations
- Status transitions are valid per lifecycle rules
- Reject invalid ops, log warnings, apply valid ops only

### Delta-Only Schema (Gemini response_json_schema)

This is passed to Gemini's Structured Outputs. It cannot represent a
full summary — only an array of operations. Adapted from the Forced
JSON report's canonical delta schema.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "mode", "ops"],
  "properties": {
    "schema_version": { "type": "string", "enum": ["delta.v1"] },
    "mode": { "type": "string", "enum": ["incremental"] },
    "ops": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["op", "id"],
        "properties": {
          "op": {
            "type": "string",
            "enum": [
              "add_fact", "add_decision", "add_topic",
              "add_action_item", "add_open_question",
              "add_pinned_memory", "update_overview",
              "update_topic_status", "complete_action_item",
              "close_open_question", "supersede_decision",
              "add_participant", "noop"
            ]
          },
          "id": { "type": "string" },
          "text": { "type": ["string", "null"] },
          "title": { "type": ["string", "null"] },
          "status": { "type": ["string", "null"] },
          "category": { "type": ["string", "null"] },
          "owner": { "type": ["string", "null"] },
          "deadline": { "type": ["string", "null"] },
          "source_message_ids": {
            "type": "array",
            "items": { "type": "string" }
          },
          "supersedes_id": { "type": ["string", "null"] },
          "notes": { "type": ["string", "null"] }
        }
      }
    }
  }
}
```

### Persistent Summary Schema (stored in channel_summaries)

This is the server-side state that delta ops are applied to. It is
never sent to Gemini as a response schema — only as read-only context
in the user prompt.

The schema is the same as previously defined (participants, overview,
active_topics, decisions, key_facts, action_items, open_questions,
pinned_memory, meta) with hash fields and source_verified flags on
protected items. See `utils/summary_schema.py` for the full definition
and empty-summary factory.

### Protected Fields and Hash Verification

Hashed at creation time using SHA-256 truncated to 8 hex characters:

| Op Type | Protected Field | Hash stored on item |
|---------|----------------|---------------------|
| `add_decision` | `text` | `text_hash` |
| `add_fact` | `text` | `text_hash` |
| `add_action_item` | `text` | `text_hash` |
| `add_pinned_memory` | `text` | `text_hash` |

Note: the delta schema uses `text` as the universal content field for
all item types, which aligns with Gemini's natural output pattern.
The persistent summary schema stores items with their type-specific
field names (`decision`, `fact`, `task`, `text`) mapped from the
delta's `text` field during the apply step.

Lifecycle rules unchanged: ADD creates with hash, SUPERSEDE retires
old item and creates new, COMPLETE/CLOSE changes status only, in-place
content modification is rejected by hash verification.

### Source Verification

When applying an `add_fact` or `add_pinned_memory` op with category
`metric`, `reference`, `constraint`, or `commitment`, verify the `text`
field appears verbatim in the source messages referenced by
`source_message_ids`. Set `source_verified: true` or `false` on the
resulting item. Items that fail are stored but flagged for review.

### Summarizer Pipeline

`utils/summarizer.py` orchestrates the full pipeline:

1. Read pre-update snapshot from `channel_summaries`.
2. Read unsummarized messages from SQLite (after `last_message_id`).
3. Batch messages if needed (configurable `batch_size`).
4. Build Gemini request: `systemInstruction` with delta rules,
   `contents` with current state snapshot + labeled messages,
   `response_mime_type` + `response_json_schema` with delta schema.
5. Call Gemini via `loop.run_in_executor()` with `ThreadPoolExecutor`.
6. Parse response — classify as delta or full summary.
7. If delta: validate schema, proceed to domain validation.
8. If full summary: canonicalize fields, diff against pre-update
   snapshot to extract delta ops, then validate.
9. Domain validation: check source IDs, reject protected rewrites,
   reject duplicate ADD IDs, validate status transitions.
10. If validation fails: log errors, attempt repair prompt (one retry).
11. Apply valid ops to pre-update snapshot.
12. Compute hashes for new protected items.
13. Run source verification on new pinned items.
14. Hash-verify all existing protected items unchanged.
15. Store updated summary. Log verification results.

Uses `temperature=0` for all calls.

**Promotion rules**: explicit decisions, preferences, commitments,
recurring facts, open questions, active tasks, filenames, paths, URLs,
version numbers, config values.

**Non-promotable**: casual filler, acknowledgments, jokes, small talk.

*Continued in Part 2: Prompts, Commands, and Implementation Plan*
