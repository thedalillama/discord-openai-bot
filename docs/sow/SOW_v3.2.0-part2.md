# SOW v3.2.0 — Structured Summary Generation (Roadmap M2)
# Part 2 of 2: Prompts, Commands, and Implementation Plan

*Continued from Part 1: Schema, Structured Output Enforcement, and
Architecture*

### System Instruction (Gemini systemInstruction)

Passed via Gemini's `systemInstruction` parameter. Contains invariant
rules that apply to every summarization call. Adapted from the Forced
JSON report's strict system instruction template.

```
You are a summarizer that emits ONLY JSON conforming to the provided
JSON Schema.

Output rules:
- Output must be a single JSON object and nothing else.
- Do not output markdown, code fences, comments, or explanations.
- Do not add keys not in the schema.
- Do not rename fields. Use EXACT field names from the schema.
- Return ONLY incremental delta operations in ops[].
- If nothing to update, return:
  {"schema_version":"delta.v1","mode":"incremental","ops":[{"op":"noop","id":"noop"}]}

Protection rules:
- Protected text must never be modified in-place. If evidence implies
  a change, emit supersede_decision with supersedes_id pointing at the
  prior decision ID plus new text.
- Do not fabricate sources. Every new item must include
  source_message_ids from the provided message labels.
- If unsure, omit the op rather than guessing.
- Preserve filenames, paths, URLs, version numbers, and numerical
  values exactly as they appear in the source messages.

Promotion rules:
- Promote: decisions, preferences, commitments, recurring facts, open
  questions, action items, filenames, paths, URLs, config values.
- Skip: casual filler, acknowledgments, jokes, small talk.
```

### User Prompt Template (per-request contents)

Passed as the user message in the Gemini call. Contains the current
state snapshot and new messages.

```
TASK:
Given CURRENT_STATE and NEW_MESSAGES, output ONLY delta ops.

CURRENT_STATE (read-only snapshot):
- overview: "..."
- decisions: [{id, text_hash, status}, ...]
- facts: [{id, text_hash, category, status}, ...]
- action_items: [{id, text_hash, status}, ...]
- open_questions: [{id, status}, ...]
- active_topics: [{id, title, status}, ...]
- participants: [{id, display_name}, ...]

NEW_MESSAGES:
[M1] Alice (2026-03-10 14:30): We should use SQLite for this.
[M2] Bob (2026-03-10 14:32): Agreed, Redis is overkill.
[M3] Alice (2026-03-10 14:35): I'll write the schema tonight.

RULES:
- Only add/close/complete/supersede where NEW_MESSAGES provide evidence.
- Every op that adds content must cite source_message_ids using
  M-labels present above.
- Do not restate CURRENT_STATE unless emitting an op about it.
```

The label-to-message-ID mapping is maintained in Python so that
`source_message_ids` M-labels in delta ops can be resolved to actual
Discord snowflake IDs when applying ops to the persistent summary.

### Repair Prompt (one retry on validation failure)

If domain validation or schema validation fails, re-prompt Gemini with
the specific errors. One retry only — if the repair also fails, log
the error and skip the update. The pre-update summary remains intact.

```
Your previous output failed validation.

VALIDATION_ERRORS:
- <specific JSON parsing or schema validation errors>
- <domain errors: rejected protected rewrite, missing source IDs, etc.>

Return ONLY corrected JSON conforming to the schema.
Do not include any other text.
```

### Normalization Fallback (full-summary recovery)

If the response is detected as a full summary (contains `overview`,
`decisions`, etc. at the top level instead of `ops`), the normalization
layer converts it to delta ops:

1. **Canonicalize fields**: `name` → `title`, `source_message_id` →
   `source_message_ids` (coerce string to array), ensure arrays are
   arrays not strings.
2. **Diff against pre-update snapshot**: identify new items (ADD ops),
   status changes (status transition ops), and protected-field changes
   (reject or detect supersession pattern).
3. **Output delta ops**: feed into the same domain validation pipeline
   as a native delta response.

See `Forced_JSON_deep-research-report.md` sections "Normalization
algorithm sketch" and "Domain-aware diffing" for the full algorithm
including `canonicalize_full_summary()` and `diff_full_to_ops()`.

### !summarize Command

`commands/summary_commands.py` (admin only):

1. Check admin permissions.
2. Show typing indicator.
3. Call `summarize_channel(channel_id)` from `utils/summarizer.py`.
4. Report: messages processed, ops applied, verification results,
   summary token count.

### !summary Command

All users. Reads from `channel_summaries` table:

1. If none exists: "No summary available. Run !summarize to generate."
2. Format key sections for Discord: overview, active topics, recent
   decisions, open action items, open questions.
3. Truncate for Discord's 2000-char limit if needed.

### Summary Storage

`channel_summaries` table (exists from v3.1.0). Functions in
`summary_store.py` (Claude Code's deviation from SOW — accepted):

```python
def save_channel_summary(channel_id, summary_json, message_count,
                         last_message_id):
def get_channel_summary(channel_id):
```

## New Files

| File | Version | Description |
|------|---------|-------------|
| `ai_providers/gemini_provider.py` | v1.0.0 | Gemini provider with structured output support |
| `utils/summarizer.py` | v1.0.0 | Pipeline: prompt build, Gemini call, classify response, normalize, validate, apply, verify |
| `utils/summary_schema.py` | v1.0.0 | Persistent summary schema, empty factory, hash utilities, delta schema definition |
| `utils/summary_normalization.py` | v1.0.0 | Field canonicalization, full-to-delta diffing, response classification |
| `utils/summary_validation.py` | v1.0.0 | Domain validation: source IDs, protected rewrites, duplicate IDs, status transitions |
| `commands/summary_commands.py` | v1.0.0 | !summarize and !summary commands |
| `docs/sow/SOW_v3.2.0.md` | — | This document (both parts) |

No new schema migration file — `channel_summaries` exists from v3.1.0.

## Modified Files

| File | Old Version | New Version | Changes |
|------|------------|-------------|---------|
| `ai_providers/__init__.py` | v1.3.0 | v1.4.0 | Add 'gemini' to factory |
| `config.py` | v1.7.0 | v1.8.0 | Add GEMINI_* and SUMMARIZER_* vars |
| `commands/__init__.py` | current | +1 | Register summary_commands |
| `requirements.txt` | current | +1 | Add google-genai |
| `STATUS.md` | v3.1.0 | v3.2.0 | Version history |
| `HANDOFF.md` | v3.1.0 | v3.2.0 | Current state |

## Unchanged Files

bot.py, raw_events.py, models.py, db_migration.py, context_manager.py,
response_handler.py, existing providers, existing commands, and the
entire `utils/history/` subsystem.

## Risk Assessment

**Medium.** Risks and mitigations:

- **Structured output not enforcing schema**: Layer 2 normalization
  catches full-summary responses and converts to deltas. Layer 3
  domain validation catches semantic errors regardless of format.
- **Gemini SDK issues**: `google-genai` is a new dependency. If
  unavailable, `!summarize` fails gracefully. Bot continues normally.
- **Invalid JSON despite structured outputs**: Parse in try/except,
  attempt one repair prompt, then skip. Pre-update summary intact.
- **Protected-field rewrites**: Hash verification detects and rejects,
  restoring from pre-update snapshot.
- **Hallucinated source IDs**: Domain validation rejects ops with
  source_message_ids not present in the provided context.
- **First-run token cost**: ~160K input tokens at Gemini Flash Lite
  pricing. Affordable for manual runs. No automated triggers in M2.
- **Output token truncation**: Delta responses are small (ops only,
  not full summary). Batching limits input size per call.

## Testing

1. **Gemini provider**: `get_provider('gemini')` returns cached
   instance, structured output params accepted, usage logged.
2. **Delta enforcement**: `!summarize` returns delta ops with
   `schema_version: "delta.v1"`, not a full summary.
3. **First summarize (100 msgs)**: Valid summary produced, stored in
   `channel_summaries`, participants/topics/decisions populated.
4. **Incremental update**: 10 new messages with a decision.
   `!summarize` processes only new messages, decision appears.
5. **Normalization fallback**: Manually bypass structured outputs and
   send a full-summary response. Verify normalization converts it to
   valid delta ops and applies correctly.
6. **Hash verification**: Edit a decision's text in the DB. Run
   `!summarize`. Verify mismatch detected, original restored.
7. **Source verification**: Pinned facts with category `reference`
   have `source_verified` flags set.
8. **Supersession**: Decision made, summarized. Decision changed in
   conversation, summarized again. Old decision `superseded`, new one
   has `supersedes_id` back-reference.
9. **Duplicate ID rejection**: Verify ADD op for existing ID is
   rejected and logged.
10. **Invalid source IDs**: Verify ops citing non-existent M-labels
    are rejected by domain validation.
11. **Repair prompt**: Force a validation error. Verify one retry
    attempted with error details, then skip if retry fails.
12. **!summary display**: Readable Discord output with overview,
    topics, decisions, action items.
13. **Empty channel**: `!summarize` with no messages. Graceful noop.
14. **Provider failure**: Unset `GEMINI_API_KEY`. Error caught cleanly.
15. **No regression**: Normal bot responses unaffected (summary not
    yet in prompts — that's M3).
