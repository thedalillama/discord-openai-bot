# HANDOFF.md
# Version 3.5.2
# Agent Development Handoff Document

## Current Status

**Branch**: claude-code
**Bot version**: v3.5.2
**Bot**: Running on GCP VM as systemd service (`discord-bot`)
**Model**: `gemini-3.1-flash-lite-preview` (in .env)
**Last deployed**: v3.5.2 (overview inflation fix)

---

## What Just Happened

### v3.5.2 — Overview Inflation Fix (DEPLOYED)
Investigation confirmed `minutes_text` IS persisted correctly in
`meta.minutes_text` by `_run_pipeline()`. The Secretary receives prior
minutes on incremental runs. The overview inflation was caused by the
Secretary prompt lacking explicit guidance to preserve the existing
overview. Fix: two lines added to SECRETARY_SYSTEM_PROMPT.

- `utils/summary_prompts_authoring.py` v1.5.0 — OVERVIEW section now
  instructs: "preserve the existing overview unless the conversation's
  purpose has fundamentally changed"

### v3.5.1 — Pipeline Unification + Classifier Dedup (TESTED)
Both cold start and incremental paths now use the same pipeline:
```
Secretary → Structurer (anyOf schema) → Classifier (dedup) → apply_ops()
```
- `utils/summarizer.py` v2.1.0 — delegates to `incremental_pipeline()`
- `utils/summarizer_authoring.py` v1.9.0 — shared `_run_pipeline()`
- `utils/summary_classifier.py` v1.3.0 — dedup against existing items
- `utils/summary_prompts.py` v1.6.0 — camelCase ops in incremental

**Test results**: Cold start 1,180 tokens → incremental 2,097 tokens.
Classifier dropped 9/9 duplicate items. Growth from overview rewrite
+ 3 genuinely new items, not duplication. Dedup confirmed working.

### v3.5.0 — anyOf Discriminated Union Schema (COMPLETE)
Gemini's constrained decoder skipped `add_topic` ops due to flat enum
+ optional fields FSM complexity. Fixed with anyOf schema, camelCase
enums, propertyOrdering. Result: 4 active + 7 archived topics.

---

## Immediate Next Steps

### 1. Merge claude-code → development
Accumulated v3.3.0 through v3.5.2. All on feature branch.

---

## Architecture Overview

### Three-Pass Pipeline (both paths)
```
Raw messages + existing minutes
  → Secretary (Gemini, natural language minutes)
  → Structurer (Gemini, anyOf JSON schema, camelCase ops)
  → translate_ops() (camelCase → snake_case)
  → Classifier (GPT-5.4 nano, KEEP/DROP/RECLASSIFY, dedup vs existing)
  → apply_ops() → verify hashes → save
```

Cold start: `cold_start_pipeline()` — no existing minutes or summary.
Incremental: `incremental_pipeline()` — passes existing minutes and
summary to Secretary and Classifier respectively.

### Schemas
- `STRUCTURER_SCHEMA` in `summary_delta_schema.py` — anyOf discriminated
  union, camelCase enums, propertyOrdering. Used by both paths.
- `DELTA_SCHEMA` in `summary_schema.py` — old flat schema. Retained for
  `_process_response()` repair calls.

### Token Budget Formula
```python
min(existing_tokens + (msg_count * 4) + 1024, 16384)
```

### Diagnostic Files
Each pipeline run saves to `data/`:
- `secretary_raw_{channel_id}.txt` — Secretary output
- `structurer_raw_{channel_id}.json` — Structurer delta ops (after translate)
- `classifier_raw_{channel_id}.json` — kept IDs + dropped items

---

## Classifier Dedup Test Results (v3.5.1)

Cold start: 539 msgs → 22 ops → 1,180 tokens
Incremental (+4 msgs): 16 ops emitted, 9 dropped as duplicates, 7 kept
Final: 543 msgs → 2,097 tokens

Structurer reused same IDs for re-emitted items. Classifier correctly
identified 9 semantically duplicate items. `_add_if_new()` silently
ignores same-ID re-emits for items the classifier kept. Token growth
was from overview expansion + 3 genuinely new items.

---

## Known Issues

### 1. _build_existing_items() Missing pinned_memory
The dedup comparison extracts from decisions, key_facts, action_items,
open_questions, and active_topics — but not pinned_memory. If the
Structurer re-emits pinned items, they won't be caught by dedup.
Low priority since pinned_memory is rarely used.

### 2. config.py Default SUMMARIZER_MODEL
Default `gemini-2.5-flash-lite` is stale. Server runs
`gemini-3.1-flash-lite-preview` via .env. Consider updating default.

### 3. WAL File Stats Bug
`get_database_stats()` reports 0.0 MB — only measures main file, not WAL.

---

## File Versions on Server

### Pipeline Files
| File | Version | Key Role |
|------|---------|----------|
| `utils/summarizer.py` | v2.1.0 | Orchestrator, delegates to pipeline |
| `utils/summarizer_authoring.py` | v1.9.0 | Three-pass pipeline (shared) |
| `utils/summary_delta_schema.py` | v1.0.0 | anyOf schema + translate_ops() |
| `utils/summary_classifier.py` | v1.3.0 | GPT-5.4 nano + existing dedup |
| `utils/summary_prompts.py` | v1.6.0 | Incremental prompt (camelCase) |
| `utils/summary_prompts_authoring.py` | v1.5.0 | Secretary/Structurer prompts |
| `ai_providers/gemini_provider.py` | v1.2.1 | use_json_schema for anyOf |

### Other Key Files
| File | Version | Role |
|------|---------|------|
| `utils/summary_schema.py` | v1.4.0 | apply_ops(), verify, DELTA_SCHEMA |
| `utils/summary_display.py` | v1.2.1 | Discord formatting, Key Facts |
| `utils/summary_store.py` | v1.1.0 | SQLite read/write |
| `utils/context_manager.py` | v1.1.0 | M3 context injection |
| `commands/summary_commands.py` | v2.2.0 | !summary commands |
| `commands/debug_commands.py` | v1.1.0 | !debug status/cleanup/noise |

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

## .env Configuration
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
OPENAI_API_KEY=[key]   # Required for GPT-5.4 nano classifier
```

---

## Roadmap

| Milestone | Status |
|-----------|--------|
| M0-M3 | ✅ Complete |
| M3.5 anyOf schema | ✅ Complete (v3.5.0) |
| M3.5 pipeline unification | ✅ Complete (v3.5.1) |
| M3.5 classifier dedup | ✅ Tested and working (v3.5.1) |
| M3.5 overview inflation fix | ✅ Deployed (v3.5.2) |
| Merge claude-code → development | Pending |
| M4 Episode segmentation | Planned |
| M5 Explainability | Planned |
| M6 Citation-backed generation | Planned |
| M7 Epoch compression | Planned |

---

## Development Rules (from AGENT.md)
1. NO CODE CHANGES WITHOUT APPROVAL
2. Discuss before coding
3. ALWAYS provide full files — no partial patches
4. INCREMENT version numbers in file heading comments
5. Keep files under 250 lines
6. Update STATUS.md and HANDOFF.md with every commit
7. Separate logical commits per change
8. Transcripts from prior sessions at `/mnt/transcripts/`
