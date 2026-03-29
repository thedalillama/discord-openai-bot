# SOW v4.2.0 — Retrieval Quality and Scalability Improvements
# Status: COMPLETE

## Overview

Four improvements shipped in this session to address retrieval quality issues
and scaling problems uncovered during testing with large channels (750–1600 messages).

---

## v4.1.7 — Batch Embedding for Backfill

### Problem
`!debug backfill` embedded one message per API call. For a channel with 1,600
messages that meant 1,600 sequential OpenAI requests — slow and rate-limit-prone.
The `batch_size` parameter on `cold_start_pipeline()` existed but was never used.

### Solution
Added `embed_texts_batch(texts, batch_size=1000)` to `embedding_store.py`.
`debug_backfill` collects all pending texts, calls the API once per 1,000 messages,
logs per-batch progress and total elapsed time. 1,600 messages now completes in ~5s.

**Bug fix included**: re-link phase previously only processed `active_topics`.
Updated to include `archived_topics`, matching `summarizer_authoring.py`.

### Files Changed
| File | From | To |
|------|------|----|
| `utils/embedding_store.py` | v1.5.0 | v1.6.0 |
| `commands/debug_commands.py` | v1.2.0 | v1.3.0 |

---

## v4.1.8 — Batched Cold Start

### Problem
`summarize_channel()` passed all messages to `cold_start_pipeline()` at once.
For a channel with 750+ messages this produced a single Secretary pass followed
by a 65K+ token Structurer response — exceeding the model's output budget.

### Solution
`summarize_channel()` now slices `all_messages[:effective_batch]` before calling
`cold_start_pipeline()`. If messages remain after the cold start saves, the saved
summary is re-read from DB and the rest continue through `_incremental_loop()`,
which already handles batching correctly. The combined result is returned to the caller.

```
Before: all 1600 messages → cold_start_pipeline() → one 65K+ Structurer call
After:  first 500 msgs → cold_start_pipeline() → incremental batch 2 (500 msgs)
          → incremental batch 3 (500 msgs) → incremental batch 4 (100 msgs)
```

### Files Changed
| File | From | To |
|------|------|----|
| `utils/summarizer.py` | v2.1.0 | v2.2.0 |

---

## v4.1.9 — Timestamps on Retrieved Messages

### Problem
Retrieved messages had no date context. Old and new discussions were
indistinguishable to the model — a discussion from 6 months ago looked the same
as one from yesterday in the injected context block.

### Solution
Every retrieved message line is now prefixed with `[YYYY-MM-DD]` extracted from
`created_at`. Applied in both retrieval paths:
- `_retrieve_topic_context()` — topic-linked messages
- `_fallback_msg_search()` — direct message similarity fallback

`find_similar_messages()` updated to return `created_at` as 4th tuple element
(was score; score is now internal-only, used for sort then stripped).
`get_topic_messages()` already returned `created_at` — no change needed.

### Files Changed
| File | From | To |
|------|------|----|
| `utils/embedding_store.py` | v1.6.0 | v1.7.0 |
| `utils/context_manager.py` | v2.1.3 | v2.1.4 |

---

## v4.1.10 — Inject Today's Date into Context

### Problem
The model knows its training cutoff date but not the current date. With timestamps
now on retrieved messages (v4.1.9), the model needed a reference point to interpret
them — e.g. whether `[2025-03-01]` was yesterday or a year ago.

### Solution
`date.today().isoformat()` injected as `Today's date: YYYY-MM-DD` at the top of
the `--- CONVERSATION CONTEXT ---` block. Applied to both the normal retrieval path
and the full-summary fallback path.

```
--- CONVERSATION CONTEXT ---
Today's date: 2026-03-29

[overview, key facts, open actions, open questions]

--- PAST MESSAGES FROM THIS CHANNEL (retrieved by topic relevance) ---
[2025-09-14] Alice: we decided to use Postgres for the database
[2026-03-28] Bob: should we revisit the database choice?
```

### Files Changed
| File | From | To |
|------|------|----|
| `utils/context_manager.py` | v2.1.4 | v2.1.5 |

---

## Constraints Observed

- Full files only — no partial diffs
- Version incremented in every changed file
- STATUS.md, HANDOFF.md, README.md, README_ENV.md, AGENT.md, CLAUDE.md updated
- No changes to summarizer pipeline structure, schema, or provider contracts
