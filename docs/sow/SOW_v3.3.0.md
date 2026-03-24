# SOW v3.3.0 — Two-Pass Summarization + Prefix Noise Filtering

**Status**: ✅ Completed (v3.3.0–v3.3.2)
**Branch**: claude-code
**Prerequisite**: v3.2.0 (Structured Summary Generation)

## Problem Statement

The v3.2.0 structured summarization pipeline produced summaries with
18,619 tokens and 214 items — overwhelmingly noise. Three root causes:

1. **Gemini Structured Outputs forced mechanical extraction.** The
   single-pass JSON-constrained pipeline treated every sentence as a
   potential fact, decision, or action item. The model had no freedom
   to exercise editorial judgment about what mattered.

2. **Bot output contaminated the input.** Previous `!summary raw`
   output was stored in Discord message history and backfilled to
   SQLite. The Secretary would read its own prior output as
   conversation content, making prompt changes have zero effect.

3. **Pattern matching for noise was fragile.** Over 30 patterns in
   `message_processing.py` tried to identify bot noise, but new
   command output constantly slipped through.

## Objectives

1. Replace single-pass JSON extraction with a two-pass Secretary →
   Structurer architecture that separates editorial judgment from
   mechanical formatting.
2. Implement a prefix-based noise filtering system (ℹ️/⚙️) that
   tags bot output at the source, replacing fragile pattern matching.
3. Add debug commands to scan, clean, and inspect bot noise.
4. Fix decision supersession so old decisions are always retired.
5. Add readable text to supersession snapshots so the model can match
   existing IDs.

## Design

### Two-Pass Architecture (v3.3.0)

**Pass 1 — Secretary:** Natural language authoring with no JSON
constraints. The model exercises editorial judgment about what belongs
in meeting minutes. Uses Gemini's 1M context to process all messages
in a single pass (no batching). Output is plain text organized by
section: OVERVIEW, PARTICIPANTS, DECISIONS, ACTION ITEMS, OPEN
QUESTIONS, KEY FACTS, ACTIVE TOPICS, ARCHIVED.

**Pass 2 — Structurer:** Mechanical JSON conversion. Takes the
Secretary's natural language minutes and converts each section into
delta ops using Gemini Structured Outputs. No editorial judgment —
just format translation.

Cold starts use Secretary → Structurer. Incremental updates use the
existing single-pass delta ops path.

### Prefix Noise Filtering (v3.3.0)

All bot command output tagged at the source:
- `ℹ️` — informational/noise (filter from API, summarizer, everything)
- `⚙️` — settings changes (keep for replay, filter from API/summarizer)

Applied to all `ctx.send()` calls across all command modules. Replaces
30+ pattern matchers with two prefix checks.

### Debug Commands (v3.3.2)

`!debug noise` — scan channel for deletable bot noise
`!debug cleanup` — delete bot noise from Discord history
`!debug status` — show summary internals (IDs, hashes, verification)

### Supersession Fix (v3.3.1)

`_supersede()` always retires old decision even with empty text field.
Snapshot includes readable text for decisions, facts, actions, and
questions so the model can match existing IDs.

## New Files

| File | Version | Description |
|------|---------|-------------|
| `utils/summary_prompts_authoring.py` | v1.1.1 | Secretary + Structurer prompts |
| `utils/summarizer_authoring.py` | v1.0.1 | Cold start two-pass pipeline |
| `utils/summary_display.py` | v1.1.0 | Paginated Discord output |
| `commands/debug_commands.py` | v1.0.0 | !debug noise/cleanup/status |

## Modified Files

| File | Old → New | Changes |
|------|-----------|---------|
| `utils/summarizer.py` | v1.5.0 → v1.9.0 | Routes cold starts to Secretary pipeline |
| `utils/summary_schema.py` | v1.2.0 → v1.4.0 | Supersession fix, empty text handling |
| `utils/summary_prompts.py` | v1.3.0 → v1.5.0 | Readable text in snapshots |
| `utils/history/message_processing.py` | v2.1.0 → v2.3.0 | Prefix filters |
| `commands/summary_commands.py` | v1.0.0 → v2.2.0 | ℹ️ prefix, raw/full subcommands |
| `commands/auto_respond_commands.py` | v2.0.0 → v2.1.0 | ℹ️/⚙️ prefixes |
| `commands/ai_provider_commands.py` | v2.0.0 → v2.1.0 | ℹ️/⚙️ prefixes |
| `commands/thinking_commands.py` | v2.1.0 → v2.2.0 | ℹ️/⚙️ prefixes |
| `commands/prompt_commands.py` | v2.0.0 → v2.1.0 | ℹ️/⚙️ prefixes |
| `commands/status_commands.py` | v2.0.0 → v2.1.0 | ℹ️ prefix |
| `commands/history_commands.py` | v2.0.0 → v2.1.0 | ℹ️ prefix |
| `commands/__init__.py` | v2.3.0 → v2.4.0 | Registers debug_commands |

## Removed Files

| File | Reason |
|------|--------|
| `commands/cleanup_commands.py` | Replaced by !debug |

## Results

| Metric | Before (v3.2.0) | After (v3.3.0) |
|--------|-----------------|-----------------|
| Token count | 18,619 | 1,871 |
| Total items | 214 | ~15 |
| Decisions | 40+ misclassified | 1-3 real |
| Supersession | Broken | Working |

## Key Learnings

- **Decisions require agreement**: "I think X" / "Agreed" = decision.
  Q&A is never a decision.
- **Fresh-from-source summarization**: Gemini's 1M context eliminates
  the ~14% semantic drift per cycle from recursive summarization.
- **Noise contamination is fatal**: Bot reading its own prior summary
  output made prompt changes have zero effect. Prefix tagging at the
  source is the only reliable fix.
- **Supersession over mutation**: Decisions are never modified in-place;
  they are retired with back-references, preserving audit history.
