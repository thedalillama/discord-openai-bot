# SOW v3.5.0 — Discriminated Union Schema for Structurer

**Status**: Proposed — awaiting approval
**Branch**: claude-code
**Prerequisite**: v3.4.0 (M3 context injection complete)

## Problem Statement

The Structurer pass (Gemini Structured Outputs) consistently refuses to
emit `add_topic` operations despite the schema including `add_topic` in
the `op` enum and the prompt containing explicit examples. This was
tested across three Gemini model tiers (Flash Lite, Flash, Pro) with
identical results: zero `add_topic` ops every time.

Research ("Gemini Structured Outputs and Complex Enum Schemas:
Systematic Underperformance Analysis") identified the root cause:
Gemini's constrained decoding uses a finite-state machine (FSM) that
creates greedy token selection bias. The flat schema with 13 enum
values and 9 optional fields creates multiplicative FSM complexity.
The decoder prefers simpler ops (add_fact, add_decision) that require
fewer fields, and systematically avoids complex ops (add_topic) that
require both `title` AND `text`.

**Key finding**: "The flat enum + optional fields pattern is the
worst-case architecture for Gemini's constrained decoder."

## Objectives

1. Replace the flat DELTA_SCHEMA with a discriminated union (`anyOf`)
   schema where each op type is a separate variant with only its
   required fields.
2. Use camelCase enum values (`addTopic` vs `add_topic`) for higher
   token probability in the constrained decoder.
3. Use `propertyOrdering` to place the `op` field first so the decoder
   commits to the operation type before generating dependent fields.
4. Use `response_json_schema` (JSON Schema format) instead of
   `response_schema` (OpenAPI format) for `anyOf` support.
5. Translate camelCase ops back to snake_case at the pipeline boundary
   so all downstream code remains unchanged.

## Design

### Discriminated Union Schema

Each op type gets its own `anyOf` variant with only the fields it
actually uses marked as `required`:

| Op Type | Required Fields |
|---------|----------------|
| `addTopic` | op, id, title, status |
| `addDecision` | op, id, text |
| `addFact` | op, id, text |
| `addActionItem` | op, id, text |
| `addOpenQuestion` | op, id, text |
| `addPinnedMemory` | op, id, text |
| `updateOverview` | op, id, text |
| `addParticipant` | op, id |
| `supersedeDecision` | op, id, supersedes_id |
| `updateTopicStatus` | op, id, status |
| `completeActionItem` | op, id |
| `closeOpenQuestion` | op, id |
| `noop` | op, id |

Each variant also includes optional fields relevant to that op type
(e.g., `addTopic` includes optional `text` for summary, `addActionItem`
includes optional `owner` and `deadline`).

### Why This Fixes the Problem

The research explains three mechanisms:

1. **Required fields**: The decoder must generate `title` and `status`
   for `addTopic` — it can't skip them. Currently all fields are
   optional and the decoder takes the path of least resistance.

2. **Discriminated union**: The FSM state space becomes the sum of
   variant complexities (additive) instead of the product of all enum
   values × all optional fields (multiplicative). Dramatically reduces
   the number of grammar states.

3. **camelCase enum values**: The constrained decoder biases toward
   high-probability tokens. `addTopic` is a more natural token sequence
   than `add_topic` (underscore splits require low-probability tokens).

4. **propertyOrdering**: Places `op` first so the decoder commits to
   the operation type before encountering field-level complexity.

### Translation Layer

`translate_ops()` in `summary_delta_schema.py` maps camelCase back
to snake_case before the ops reach `apply_ops()`, the classifier,
or any other downstream code:

```python
_ENUM_MAP = {
    "addTopic": "add_topic",
    "addFact": "add_fact",
    "addDecision": "add_decision",
    ...
}
```

This means zero changes to `apply_ops()`, `filter_ops()`, display
code, or the incremental path. The translation is a one-line call
in `cold_start_pipeline()`.

### Provider Change

The Gemini provider currently passes schemas via `response_schema`
(OpenAPI format). The `anyOf` keyword is better supported in
`response_json_schema` (JSON Schema format). The provider needs a
new parameter to select which config key to use.

## New Files

| File | Version | Description |
|------|---------|-------------|
| `utils/summary_delta_schema.py` | v1.0.0 | `anyOf` discriminated union schema, `translate_ops()`, camelCase enum map |
| `docs/sow/SOW_v3.5.0.md` | — | This document |

## Modified Files

| File | Old Version | New Version | Changes |
|------|-------------|-------------|---------|
| `utils/summarizer_authoring.py` | v1.5.0 | v1.6.0 | Import STRUCTURER_SCHEMA, call translate_ops() after Structurer |
| `utils/summary_prompts_authoring.py` | v1.3.0 | v1.4.0 | camelCase op names in STRUCTURER_SYSTEM_PROMPT |
| `ai_providers/gemini_provider.py` | v1.1.0 | v1.2.0 | Support `response_json_schema` config key for `anyOf` schemas |

## Unchanged Files

`summary_schema.py` (DELTA_SCHEMA retained for incremental path),
`summary_classifier.py`, `summary_display.py`, `context_manager.py`,
`summary_store.py`, `apply_ops()`, all command modules, all other
providers, `bot.py`, `config.py`.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `anyOf` not supported by model | Low | High | Research confirms support since Nov 2025; test before commit |
| Schema too complex for FSM | Low | Medium | Each variant is simple; total complexity is additive |
| camelCase translation missed | Low | Medium | `translate_ops()` is called once; all downstream sees snake_case |
| Provider change breaks other calls | Low | High | New param is additive; existing `response_json_schema` kwarg unchanged |
| Incremental path affected | None | — | Incremental path still uses old DELTA_SCHEMA via `summarizer.py` |

## Testing

1. Deploy all four files, restart bot
2. `!summary clear` + `!summary create`
3. Check `data/structurer_raw_{channel_id}.json` — verify `addTopic`
   ops are present
4. Check `!summary` — verify topics appear in output
5. Check `!debug status` — verify topics show with correct IDs
6. Verify classifier handles the translated ops correctly
7. Verify `!summary raw` shows clean Secretary output (no looping)
8. If `anyOf` fails with 400 error, fall back to flat schema with
   camelCase only (partial fix)

## Test Results

**The anyOf discriminated union schema works.** The Structurer produced
23 ops including 4 active topics and 7 archived topics — matching the
Secretary output exactly. This is up from zero topics with the flat
schema across three different Gemini model tiers.

Results from 517-message cold start:
- Secretary: clean output, no repetition loop (max_tokens cap working)
- Structurer: 23 ops including 11 add_topic (4 active, 7 archived)
- Classifier: kept 21, dropped 2 (dedup: Database Decision topic
  overlapped with decision item, archived AI pricing duplicated active)
- translate_ops(): camelCase → snake_case translation worked correctly
- All downstream code (apply_ops, display, debug) handled topics

## Lessons Learned

### 1. Gemini's constrained decoder has systematic enum bias
The flat DELTA_SCHEMA with 13 enum values and 9 optional fields caused
Gemini to systematically avoid `add_topic` ops across all model tiers
(Flash Lite, Flash, Pro). The model knew about `add_topic` when queried
in plain text but never emitted it under structured outputs mode. This
is not a model intelligence issue — it's an FSM state space issue.

### 2. Schema descriptions made things worse
Adding `description` fields to the schema (per Google's recommendation)
caused Gemini to produce even fewer op types. The descriptions added
complexity to the FSM without helping the decoder select the right
enum values. Reverted immediately.

### 3. The anyOf pattern is the correct fix
Switching from flat enum + optional fields to discriminated union
(`anyOf`) with per-variant required fields eliminated the problem
completely. Each variant has only the fields it needs, reducing FSM
complexity from multiplicative to additive.

### 4. response_json_schema vs response_schema matters
The `anyOf` keyword is only supported via `response_json_schema`
(JSON Schema format), not `response_schema` (OpenAPI format). The
Gemini provider needed a new `use_json_schema` parameter to select
the correct config key.

### 5. camelCase enum values help token probability
The constrained decoder biases toward high-probability tokens.
`addTopic` (camelCase) is a more natural token sequence than
`add_topic` (snake_case with underscore). Combined with the anyOf
pattern, this ensures the decoder doesn't avoid any enum values.

### 6. Always provide complete files when modifying providers
The `_convert_messages()` function was accidentally broken when
rewriting `gemini_provider.py` — plain dicts were used instead of
`types.Content` and `types.Part` objects. The original SDK-specific
format must be preserved exactly. Fixed in v1.2.1.

### 7. Test scripts must match production filtering
`test_pipeline.py` filtered out bot messages (`is_bot_author`) while
production included them (517 vs 248 messages). This masked the
Gemini repetition loop bug. Test scripts should use the same filtering
as production code.

### 8. Classifier may over-aggregate related items
The classifier dropped a Database Decision topic because it overlapped
with the decision item. But the topic contains richer narrative context
than the one-line decision. Future work: topics should be containers
for related items (decisions, facts, actions), not peers that get
deduplicated against them.

## Future Work

If the `anyOf` schema works, consider:
- Migrating the incremental path to use the same schema
- Refactoring downstream code to use camelCase natively (eliminating
  the translation layer)
- Topic-centric schema: items nested under parent topics with snowflake
  message IDs as immutable evidence anchors
- Classifier tuning: keep topics that provide context for decisions
- Tune classifier to never drop action items with assigned owners
