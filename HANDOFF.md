# HANDOFF.md
# Version 3.4.0
# Agent Development Handoff Document

## Current Status

**Branch**: claude-code
**Bot version**: v3.4.0
**Bot**: Running on GCP VM as systemd service (`discord-bot`)
**Last completed**: v3.4.0 — M3 Context Integration + KEY FACTS
**Next**: Archived bloat fix, then M4 (episode segmentation)

---

## Recent Completed Work

### v3.4.0 — M3 Context Integration + KEY FACTS
- **MODIFIED**: `utils/context_manager.py` v1.1.0 — loads channel summary,
  appends to system prompt as `--- CONVERSATION CONTEXT ---` block
- **MODIFIED**: `utils/summary_display.py` v1.2.1 — `format_summary_for_context()`
  for plain text injection; Key Facts in default `!summary` view
- **MODIFIED**: `utils/summary_prompts_authoring.py` v1.2.0 — KEY FACTS section
  in Secretary prompt; Structurer maps to `add_fact` ops
- **ADDED**: `test_pipeline.py` — runs Secretary + Structurer outside Discord
- **ADDED**: `test_summary.py` — inspects stored summary + interactive Q&A
- **MODIFIED**: `README_ENV.md` v3.4.0 — Gemini/summarizer variables

### v3.3.2 — Debug Command Group
- **NEW**: `commands/debug_commands.py` v1.0.0 — !debug noise/cleanup/status
- **MODIFIED**: `commands/__init__.py` v2.4.0
- **REMOVED**: `commands/cleanup_commands.py`

### v3.3.1 — Supersession Fix + Readable Snapshots
- **MODIFIED**: `utils/summary_schema.py` v1.4.0 — always retire old decision
- **MODIFIED**: `utils/summary_prompts.py` v1.5.0 — readable text in snapshots
- **MODIFIED**: `utils/summary_prompts_authoring.py` v1.1.2 — skip M-labels

### v3.3.0 — Two-Pass Summarization + Prefix Noise Filtering
- Secretary/Structurer two-pass architecture
- ℹ️/⚙️ prefix system across all command modules
- Result: 18,619 → 1,871 tokens for 483 messages

### v3.2.x — Structured Summary Generation (M2)
### v3.1.x — Schema Extension & Enhanced Capture
### v3.0.0 — SQLite Message Persistence Layer

---

## Summarization Architecture

### Two-Pass Pipeline (Cold Start)
```
Raw messages → Secretary (natural language minutes, no JSON)
            → Structurer (JSON delta ops via Gemini Structured Outputs)
            → apply_ops() → verify hashes → save to channel_summaries
```
- Summarizer model: `gemini-3.1-flash-lite-preview` (via .env override)
- Single pass for cold starts (SUMMARIZER_BATCH_SIZE=500)

### Incremental Updates
```
New messages + readable CURRENT_STATE snapshot → Gemini Structured Outputs
            → delta ops JSON → apply_ops() → verify → save
```

### M3 Context Injection
```
System prompt + "--- CONVERSATION CONTEXT ---" + formatted summary
→ sent as single system message to conversation provider
→ bot has memory of decisions, topics, facts, actions, questions
```

### Noise Filtering
```
ℹ️ = noise (filter everywhere)
⚙️ = settings (keep for replay, filter from API/summarizer)
Legacy patterns retained for pre-prefix messages
```

### Hash Protection
- Protected: decisions, key_facts, action_items, pinned_memory
- SHA-256 truncated to 8 hex chars, assigned at creation
- Supersession retires old, creates new — never modifies in-place

---

## Known Issues

### Archived Items Bloating Summary
Secretary produces 50+ archived one-liners. Structurer converts each to
a separate `add_topic` with `status: "archived"`. Causes token bloat
(3,639 tokens vs 1,871 clean). Fix: condense ARCHIVED to 5-6 categories.

### config.py Default SUMMARIZER_MODEL
Default `gemini-2.5-flash-lite` is stale. Server runs
`gemini-3.1-flash-lite-preview` via .env. Consider updating default.

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
| `!debug status` | admin | Summary internals (IDs, hashes) |
| `!status` | all | Bot settings for this channel |
| `!autorespond` | all/admin | Auto-response toggle |
| `!ai` | all/admin | AI provider switch |
| `!thinking` | all/admin | DeepSeek thinking display |
| `!prompt` | all/admin | System prompt view/set/reset |
| `!history` | all | View/clean/reload history |

---

## .env Configuration (current server)
```
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=sk-[key]
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-reasoner
OPENAI_COMPATIBLE_CONTEXT_LENGTH=64000
OPENAI_COMPATIBLE_MAX_TOKENS=8000
CONTEXT_BUDGET_PERCENT=80
SUMMARIZER_PROVIDER=gemini
SUMMARIZER_MODEL=gemini-3.1-flash-lite-preview
SUMMARIZER_BATCH_SIZE=500
GEMINI_API_KEY=[key]
GEMINI_MAX_TOKENS=32768
```

---

## Roadmap

| Milestone | Description | Status |
|-----------|-------------|--------|
| M0 | Merge dev → main | ✅ Complete |
| M1 | Schema extension v3.1.0 | ✅ Complete |
| M2 | Structured summary generation | ✅ Complete (v3.3.0) |
| M3 | Context integration | ✅ Complete (v3.4.0) |
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
