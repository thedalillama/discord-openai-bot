# SOW v3.4.0 — M3 Context Integration + Classifier + Diagnostics

**Status**: ✅ Completed
**Branch**: claude-code
**Prerequisite**: v3.3.0 (Two-Pass Summarization)

## Problem Statement

Three issues after v3.3.0:

1. **No memory in conversations.** The bot had a structured summary
   stored in SQLite but never used it. Conversation responses had no
   access to prior decisions, facts, or action items.

2. **Summary quality issues.** The Structurer produced misclassified
   items (scientific facts as decisions, transient queries as topics)
   and the Secretary missed personal details (favorite number, age).

3. **No visibility into pipeline behavior.** No way to see what the
   Secretary, Structurer, or Classifier produced at each stage without
   checking DEBUG logs.

## Objectives

1. Inject the channel summary into the system prompt so the bot has
   conversational memory (M3 milestone).
2. Add KEY FACTS section to Secretary prompt for personal details.
3. Add GPT-5.4 nano classifier as quality control pass after Structurer.
4. Add diagnostic file output for each pipeline stage.
5. Cap Secretary output tokens to prevent Gemini repetition loop.

## Design

### M3 Context Injection

`context_manager.py` loads the channel summary and appends it to the
system prompt as a `--- CONVERSATION CONTEXT ---` block. The combined
system message counts against the token budget normally. The bot can
now answer questions from summary memory ("what database are we using?").

### KEY FACTS Section

Added to Secretary prompt between OPEN QUESTIONS and ACTIVE TOPICS.
Captures personal details (favorite number, age, location) that would
otherwise be lost to ARCHIVED one-liners. Includes GOOD/BAD examples
to guide the model.

### GPT-5.4 Nano Classifier (Pass 3)

After the Structurer produces delta ops, a classification pass using
OpenAI's GPT-5.4 nano model validates each item:
- **KEEP**: correctly classified, retain
- **DROP**: duplicate or noise (individual bot responses as topics)
- **RECLASSIFY**: wrong category, move to correct one

Cost: ~$0.0002 per run. Fail-safe: if the call fails, all ops are
kept (same as before).

Dropped items stored in `meta.classifier_drops` for audit trail.
`!debug status` displays them with 🗑️ icons.

### Diagnostic Files

Each pipeline stage saves its output to `data/`:
- `data/secretary_raw_{channel_id}.txt` — exact Gemini output
- `data/structurer_raw_{channel_id}.json` — delta ops before classifier
- `data/classifier_raw_{channel_id}.json` — kept IDs and dropped items

### Scaled max_output_tokens

Secretary output budget scales with message count:
`min(1024 + (msg_count * 4), 16384)`

Prevents Gemini's known repetition loop (documented as a known bug
across all Gemini model tiers) from burning 32K+ tokens on the
ARCHIVED section. For 517 messages: 3,092 tokens instead of 32,768.

## New Files

| File | Version | Description |
|------|---------|-------------|
| `utils/summary_classifier.py` | v1.1.0 | GPT-5.4 nano KEEP/DROP/RECLASSIFY with dedup rules |

## Modified Files

| File | Old → New | Changes |
|------|-----------|---------|
| `utils/context_manager.py` | v1.0.0 → v1.1.0 | M3: load summary, inject into system prompt |
| `utils/summary_display.py` | v1.1.0 → v1.2.1 | format_summary_for_context(); Key Facts in default view |
| `utils/summary_prompts_authoring.py` | v1.1.2 → v1.3.0 | KEY FACTS section; topic examples in Structurer prompt |
| `utils/summarizer_authoring.py` | v1.0.1 → v1.5.0 | Three-pass pipeline; classifier; diagnostic files; scaled max_tokens |
| `commands/debug_commands.py` | v1.0.0 → v1.1.0 | Classifier drops in !debug status |
| `README_ENV.md` | v3.0.0 → v3.4.0 | Gemini/summarizer variables |

## Results

| Metric | v3.3.0 | v3.4.0 |
|--------|--------|--------|
| Token count | 1,871 | 646-1,214 |
| Bot memory | None | Answers from summary |
| Classifier cost | N/A | $0.0002/run |
| Diagnostic visibility | DEBUG logs only | Files in data/ |

## Key Learnings

- **Gemini repetition loop is a known bug.** With 517 messages
  (including bot messages), the Secretary enters an infinite loop
  in the ARCHIVED section, repeating the same block of entries until
  hitting max_output_tokens. The raw output was 64,920 chars with
  "Amodei family" appearing 78 times. Scaling max_output_tokens with
  message count prevents the loop from burning excessive tokens.

- **Test scripts must match production filtering.** `test_pipeline.py`
  filtered bot messages (248 messages), but production included them
  (517 messages). The test didn't catch the repetition loop because
  it ran with half the input.

- **GPT-5.4 nano is excellent for classification.** At $0.03/1M input
  and $0.15/1M output, the classifier costs fractions of a cent per
  run and correctly identifies noise, duplicates, and misclassifications.

- **Classifier can be too aggressive.** Without clear rules, it dropped
  all topics (v1.0.0). Updated prompt to respect Secretary's judgment —
  only drop duplicates and bot-response-repackaged-as-topic noise.

- **Action items with owners should not be dropped.** The classifier
  dropped "Update README with database choice" — a legitimate action.
  Future work: add rule that action items with assigned owners are
  always KEEP.

- **Structurer skips add_topic ops.** Gemini's constrained decoder
  systematically avoids complex ops (add_topic requires both title
  and text). This issue persisted across Flash Lite, Flash, and Pro
  models. Root cause identified; fix deferred to SOW v3.5.0.
