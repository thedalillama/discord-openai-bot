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

## Future Work

If the `anyOf` schema works, consider:
- Migrating the incremental path to use the same schema
- Refactoring downstream code to use camelCase natively (eliminating
  the translation layer)
- Adding `propertyOrdering` guidance to the research document
