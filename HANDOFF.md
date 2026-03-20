# HANDOFF.md
# Version 3.3.2
# Agent Development Handoff Document

## Current Status

**Branch**: claude-code
**Bot version**: v3.3.2
**Bot**: Running on GCP VM as systemd service (`discord-bot`)
**Last completed**: v3.3.2 — Debug command group
**Next**: M3 — Context integration (inject minutes into conversation context)

---

## Recent Completed Work

### v3.3.2 — Debug Command Group
- **NEW**: `commands/debug_commands.py` v1.0.0 — consolidates !cleanup into
  !debug with subcommands: noise (scan), cleanup (delete), status (internals)
- **MODIFIED**: `commands/__init__.py` v2.4.0 — registers debug_commands
- **REMOVED**: `commands/cleanup_commands.py` — replaced by !debug

### v3.3.1 — Supersession Fix + Readable Snapshots
- **MODIFIED**: `utils/summary_schema.py` v1.4.0 — `_supersede()` always
  retires old decision even with empty text field
- **MODIFIED**: `utils/summary_prompts.py` v1.5.0 — snapshot includes readable
  text (decision, fact, task, question) so model can match IDs; re-exports
  authoring prompts
- **MODIFIED**: `utils/summary_prompts_authoring.py` v1.1.2 — M-labels in
  WHAT TO SKIP list

### v3.3.0 — Two-Pass Summarization + Prefix Noise Filtering

**Two-pass Secretary/Structurer architecture:**
- **NEW**: `utils/summary_prompts_authoring.py` v1.1.1 — Secretary prompt
  (unstructured natural language minutes) + Structurer prompt (JSON conversion).
  Decision defined as agreement-on-action, not fact lookup.
- **NEW**: `utils/summarizer_authoring.py` v1.0.1 — Cold start pipeline:
  Secretary writes minutes in single pass (all messages at once), Structurer
  converts to JSON delta ops.
- **NEW**: `utils/summary_display.py` v1.1.0 — Paginated output with ℹ️ prefix
- **MODIFIED**: `utils/summarizer.py` v1.9.0 — routes cold starts to Secretary
  pipeline (summarizer_authoring), incremental to delta ops
- **MODIFIED**: `commands/summary_commands.py` v2.2.0 — !summary raw, !summary
  full subcommands; ℹ️ prefix on all output

**Prefix noise filtering system:**
- **MODIFIED**: All command modules with ℹ️ (noise) or ⚙️ (settings) prefix
- **MODIFIED**: `utils/history/message_processing.py` v2.3.0 — `is_noise_message()`,
  `is_settings_message()`, `is_admin_output()` prefix checks + legacy fallback
- **NEW**: `commands/cleanup_commands.py` v1.0.0 — !cleanup scan/run for
  removing pre-prefix bot noise (later moved to !debug)

**Result**: 18,619 tokens → 1,871 tokens. 214 items → ~15 meaningful entries.

### v3.2.3 — Summary Quality & Bot Message Filtering
### v3.2.2 — Three-Layer Enforcement Architecture
### v3.2.0 — Structured Summary Generation (M2)
### v3.1.1 — Code Quality: realtime_settings_parser.py split
### v3.1.0 — Schema Extension & Enhanced Capture
### v3.0.0 — SQLite Message Persistence Layer

---

## Summarization Architecture

### Two-Pass Pipeline (Cold Start)
```
Raw messages → Secretary (natural language minutes, no JSON)
            → Structurer (mechanical JSON conversion via Gemini Structured Outputs)
            → apply_ops() → verify hashes → save to channel_summaries
```
- Secretary uses Gemini 3.1 Flash Lite Preview (`gemini-3.1-flash-lite-preview`)
- Single pass for cold starts (all messages in one call, no batching)
- SUMMARIZER_BATCH_SIZE=500 in .env ensures single pass

### Incremental Updates
```
New messages → build_prompt() with readable CURRENT_STATE snapshot
            → Gemini Structured Outputs (delta ops JSON)
            → apply_ops() → verify hashes → save
```
- Uses the delta ops path directly (no Secretary)
- Snapshot includes readable text for decision/fact/action/question so
  model can match existing IDs for supersede ops

### Noise Filtering (Three Layers + Prefix)
```
Layer 1 — Runtime:   add_response_to_history() checks is_history_output()
Layer 2 — Load time: discord_converter.py checks is_history_output()
Layer 3 — API build: prepare_messages_for_api() checks both filters
Layer 4 — Prefix:    ℹ️ = noise (filter everywhere), ⚙️ = settings (keep for replay)
```

### Summarizer Input Filtering
- `not m.is_bot_author` — excludes bot messages from summarization
- `is_noise_message()` / `is_settings_message()` — excludes admin output
- Messages starting with `!` — excluded as commands

### Hash Protection
- Protected fields: decisions, key_facts, action_items, pinned_memory
- SHA-256 truncated to 8 hex chars, assigned at creation
- Supersession retires old item, creates new — never modifies in-place
- `verify_protected_hashes()` restores from snapshot on mismatch

### Key Design Decisions
- **Decision = agreement on action**: "I think X" / "Agreed" → decision.
  "What is X?" / "X is Y" → fact/topic, NOT a decision.
- **Fresh-from-source > recursive**: Gemini's 1M context sends all raw
  messages directly, eliminating recursive summary drift
- **Secretary writes freely**: No JSON constraint in Pass 1 lets the model
  exercise judgment about what matters
- **Prefix-based filtering**: Single ℹ️/⚙️ prefix check replaces 30+ pattern matchers

---

## Message Persistence Architecture

- **Database**: SQLite with WAL mode (`data/messages.db`)
- **Real-time capture**: `raw_events.py` on_message listener stores all messages
  including bot messages (with `is_bot_author` flag)
- **Backfill**: On startup, up to 10,000 messages per channel from Discord API
- **Soft delete**: `is_deleted=1`, never hard-deleted
- **Migration**: `db_migration.py` applies `schema/NNN.sql` files sequentially

---

## .env Configuration (Summarization)
```
SUMMARIZER_PROVIDER=gemini
SUMMARIZER_MODEL=gemini-3.1-flash-lite-preview
SUMMARIZER_BATCH_SIZE=500
GEMINI_API_KEY=<key>
GEMINI_MAX_TOKENS=32768
```

---

## Commands Reference

| Command | Access | Description |
|---------|--------|-------------|
| `!summary` | all | Show current channel summary |
| `!summary full` | all | All sections including facts/archived |
| `!summary raw` | all | Secretary's natural language minutes |
| `!summary create` | admin | Run summarization |
| `!summary clear` | admin | Delete stored summary |
| `!debug noise` | admin | Scan for bot noise |
| `!debug cleanup` | admin | Delete bot noise from Discord |
| `!debug status` | admin | Show summary internals (IDs, hashes) |
| `!status` | all | Bot settings for this channel |
| `!autorespond` | all/admin | Auto-response status/toggle |
| `!ai` | all/admin | AI provider status/switch |
| `!thinking` | all/admin | DeepSeek thinking display |
| `!prompt` | all/admin | System prompt view/set/reset |
| `!history` | all | View/clean/reload conversation history |

---

## Development Rules (from AGENT.md)
1. NO CODE CHANGES WITHOUT APPROVAL
2. ALL DEVELOPMENT WORK IN development BRANCH (or feature branches)
3. main BRANCH IS FOR STABLE CODE ONLY
4. DISCUSS FIRST, CODE SECOND
5. ALWAYS provide full files — no partial patches
6. INCREMENT version numbers in file heading comments
7. Keep files under 250 lines
8. Test before committing
9. Update STATUS.md and HANDOFF.md with every commit

---

## Roadmap (Remaining Milestones)

| Milestone | Description | Status |
|-----------|-------------|--------|
| M0 | Merge dev → main | ✅ Complete |
| M1 | Schema extension v3.1.0 | ✅ Complete |
| M2 | Structured summary generation | ✅ Complete (v3.3.0) |
| M3 | Context integration | **NEXT** |
| M4 | Episode segmentation and retrieval | Planned |
| M5 | Explainability and context receipts | Planned |
| M6 | Citation-backed generation | Planned |
| M7 | Epoch compression | Planned |

### M3: Context Integration (Next)
Inject summary minutes into `build_context_for_provider()` between system
prompt and recent messages. The bot will use its conversational memory
when responding, giving it awareness of decisions, action items, and
topic history without needing the full message history in context.
