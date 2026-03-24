# HANDOFF.md
# Version 3.5.0
# Agent Development Handoff Document

## Current Status

**Branch**: claude-code
**Bot version**: v3.5.0
**Bot**: Running on GCP VM as systemd service (`discord-bot`)
**Last completed**: v3.5.0 — anyOf discriminated union schema
**Next**: Incremental path migration, merge to development

---

## Recent Completed Work

### v3.5.0 — Discriminated Union Schema (SOW v3.5.0)
- **NEW**: `utils/summary_delta_schema.py` v1.0.0 — anyOf schema with
  camelCase enums, propertyOrdering, per-variant required fields
- **MODIFIED**: `utils/summarizer_authoring.py` v1.6.0 — STRUCTURER_SCHEMA
  + translate_ops() for camelCase → snake_case
- **MODIFIED**: `utils/summary_prompts_authoring.py` v1.4.0 — camelCase
  op names in Structurer prompt
- **MODIFIED**: `ai_providers/gemini_provider.py` v1.2.1 — use_json_schema
  kwarg for anyOf support
- **MODIFIED**: `utils/summary_classifier.py` v1.2.0 — protect topics
  with decisions and action items with owners
- **ROOT CAUSE**: Gemini's FSM constrained decoder systematically avoided
  add_topic ops due to flat enum + optional fields architecture. anyOf
  discriminated union reduces FSM complexity from multiplicative to additive.

### v3.4.0 — M3 Context Integration + KEY FACTS
- M3 complete: summary injected into system prompt
- GPT-5.4 nano classifier, diagnostic files, scaled max_tokens

### v3.3.0-3.3.2 — Two-Pass Summarization + Noise Filtering
- Secretary/Structurer architecture, ℹ️/⚙️ prefix system
- Debug commands, supersession fix

---

## Summarization Architecture

### Three-Pass Pipeline (Cold Start)
```
Raw messages → Secretary (Gemini, natural language minutes)
            → Structurer (Gemini, anyOf JSON schema, camelCase ops)
            → translate_ops() (camelCase → snake_case)
            → Classifier (GPT-5.4 nano, KEEP/DROP/RECLASSIFY)
            → apply_ops() → verify hashes → save
```
- Secretary model: `gemini-3.1-flash-lite-preview` (via .env)
- Structurer uses `STRUCTURER_SCHEMA` (anyOf discriminated union)
  passed via `response_json_schema` (JSON Schema format)
- Classifier cost: ~$0.0002 per run
- Diagnostic files saved to `data/` at each stage

### Incremental Updates
```
New messages + CURRENT_STATE snapshot → Gemini Structured Outputs
            → delta ops JSON (old flat DELTA_SCHEMA)
            → apply_ops() → verify → save
```
Note: incremental path still uses old DELTA_SCHEMA — migration planned.

### M3 Context Injection
```
System prompt + "--- CONVERSATION CONTEXT ---" + formatted summary
→ sent as single system message to conversation provider
```

---

## Key Design Decisions

### anyOf Schema (v3.5.0)
Gemini's constrained decoder uses a finite-state machine (FSM) that
creates greedy token selection bias. The flat schema with 13 enum
values and 9 optional fields was the worst-case architecture. The
anyOf discriminated union gives each op type its own variant with
only required fields, reducing FSM complexity from multiplicative
to additive. Combined with camelCase enums (higher token probability)
and propertyOrdering (op field first).

### Two Schemas
- `DELTA_SCHEMA` in `summary_schema.py` — flat schema, used by
  incremental path in `summarizer.py`
- `STRUCTURER_SCHEMA` in `summary_delta_schema.py` — anyOf schema,
  used by cold start Structurer in `summarizer_authoring.py`

### Two JSON Schema Paths in Provider
- `response_schema` — OpenAPI format (default, used by incremental)
- `response_json_schema` — JSON Schema format (use_json_schema=True,
  used by Structurer for anyOf support)

---

## Commands Reference

| Command | Access | Description |
|---------|--------|-------------|
| `!summary` | all | Show channel summary |
| `!summary full` | all | All sections including archived |
| `!summary raw` | all | Secretary's natural language minutes |
| `!summary create` | admin | Run summarization |
| `!summary clear` | admin | Delete stored summary |
| `!debug noise` | admin | Scan for bot noise |
| `!debug cleanup` | admin | Delete bot noise from Discord |
| `!debug status` | admin | Summary internals + classifier drops |

---

## .env Configuration (current server)
```
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=sk-[key]
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-reasoner
SUMMARIZER_PROVIDER=gemini
SUMMARIZER_MODEL=gemini-3.1-flash-lite-preview
SUMMARIZER_BATCH_SIZE=500
GEMINI_API_KEY=[key]
GEMINI_MAX_TOKENS=32768
OPENAI_API_KEY=[key]
```

---

## Roadmap

| Milestone | Description | Status |
|-----------|-------------|--------|
| M0 | Merge dev → main | ✅ Complete |
| M1 | Schema extension v3.1.0 | ✅ Complete |
| M2 | Structured summary generation | ✅ Complete (v3.2.0) |
| M3 | Context integration | ✅ Complete (v3.4.0) |
| M3.5 | anyOf schema fix | ✅ Complete (v3.5.0) |
| M4 | Episode segmentation and retrieval | Planned |
| M5 | Explainability and context receipts | Planned |
| M6 | Citation-backed generation | Planned |
| M7 | Epoch compression | Planned |

---

## Development Rules (from AGENT.md)
1. NO CODE CHANGES WITHOUT APPROVAL
2. ALL DEVELOPMENT IN development OR feature branches
3. main BRANCH IS FOR STABLE CODE ONLY
4. DISCUSS FIRST, CODE SECOND
5. ALWAYS provide full files — no partial patches
6. INCREMENT version numbers in file heading comments
7. Keep files under 250 lines
8. Test before committing
9. Update STATUS.md and HANDOFF.md with every commit
