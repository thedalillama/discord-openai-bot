# SOW v4.0.0 — Topic-Based Semantic Retrieval
# Part 2 of 2: Read Path, Files, Config, Risk, Testing, Build Order

## Read Path: Semantic Retrieval in `context_manager.py`

Replace `_load_summary_text()` with a two-part context builder:

**Part 1 — Always-on context** (injected every time):
- Overview (from summary JSON)
- Open action items (from summary JSON)
- Open questions (from summary JSON)
- Key facts (from summary JSON)

These are universally relevant and small. Estimated ~200-400 tokens.

**Part 2 — Retrieved topic context** (semantic matching):
1. Embed the most recent user message
2. Call `find_relevant_topics(embedding, channel_id, top_k=5)`
3. For each matched topic, fetch its linked messages from
   `topic_messages` → `messages`
4. Format retrieved messages as conversation context
5. Inject after the always-on block, before recent messages

```python
def build_context_for_provider(channel_id, provider):
    # ... existing budget calculation ...

    # Part 1: Always-on context
    always_on = _build_always_on_context(channel_id)

    # Part 2: Semantic retrieval
    recent_user_msg = _get_latest_user_message(conversation_msgs)
    if recent_user_msg:
        retrieved = _retrieve_topic_messages(
            channel_id, recent_user_msg, budget_remaining)
    else:
        retrieved = ""

    combined = (
        f"{system_prompt}\n\n"
        f"--- CONVERSATION CONTEXT ---\n{always_on}\n\n"
        f"--- RELEVANT HISTORY ---\n{retrieved}"
    )
    # ... existing budget trimming ...
```

**Budget awareness**: Retrieved messages count against the token
budget. If 5 topics × 20 messages × 50 tokens = 5,000 tokens, that
leaves less room for recent messages. The existing budget trimming
logic handles this naturally.

**Deduplication**: Retrieved topic messages may overlap with the
recent message window. Filter out any message IDs already in the
recent conversation messages before injecting.

**Hot path latency**: One embedding API call (~100-200ms) + SQLite
queries (~1ms) + cosine similarity (~0.01ms). Invisible against
2-5 second LLM generation time.

**Fallback**: If embedding fails or no topics exist, fall back to
injecting the full summary (current v3.5.x behavior). The bot never
fails to respond because of retrieval issues.

## New Files

| File | Version | Description |
|------|---------|-------------|
| `utils/embedding_store.py` | v1.0.0 | Embed, store, retrieve, similarity, topic-message linkage |
| `schema/004.sql` | — | topics, topic_messages, message_embeddings tables |
| `docs/sow/SOW_v4.0.0.md` | — | This document (both parts) |

## Modified Files

| File | Old Version | New Version | Changes |
|------|-------------|-------------|---------|
| `utils/raw_events.py` | v1.2.0 | v1.3.0 | Embed messages on arrival |
| `utils/summarizer_authoring.py` | v1.9.0 | v1.10.0 | Store topics + link by embedding after pipeline |
| `utils/context_manager.py` | v1.1.0 | v2.0.0 | Semantic retrieval replaces full summary injection |
| `utils/summary_display.py` | v1.2.1 | v1.3.0 | `format_always_on_context()` for slim injection |
| `config.py` | v1.11.0 | v1.12.0 | RETRIEVAL_TOP_K, EMBEDDING_MODEL, TOPIC_MSG_LIMIT env vars |
| `commands/debug_commands.py` | v1.1.0 | v1.2.0 | `!debug backfill_embeddings` command |

## Unchanged Files

The entire summarization pipeline (Secretary, Structurer, Classifier,
apply_ops, summary_schema, summary_prompts, summary_delta_schema).
The summary JSON continues to be generated and stored — the topics
table is an additional retrieval index, not a replacement. All
conversation providers, all other commands, bot.py, noise filtering,
the history subsystem.

The `source_message_ids` field on decisions, facts, and action items
is unchanged — it remains for audit trail and source verification.
It is NOT used for topic-message linkage (topics use embedding
similarity instead).

## Configuration

New `.env` variables:

```
RETRIEVAL_TOP_K=5                   # Topics to retrieve per query
EMBEDDING_MODEL=text-embedding-004  # Gemini embedding model
TOPIC_MSG_LIMIT=20                  # Messages linked per topic
```

All have sensible defaults. No new API keys — uses existing
`GEMINI_API_KEY`.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Gemini embedding API unavailable | Low | Medium | Fall back to full summary injection |
| Embedding latency on hot path | Low | Low | ~100-200ms vs 2-5s generation |
| Irrelevant topics retrieved | Medium | Low | Top-K with threshold; always-on covers essentials |
| Topic-message links imprecise | Medium | Medium | Embedding similarity is fuzzy; tune TOPIC_MSG_LIMIT |
| Message embedding backfill slow | Low | Low | One-time; Gemini batch; free tier |
| context_manager.py exceeds 250 lines | Medium | Low | Extract retrieval to embedding_store.py |

## Testing

### Phase 1 — Schema and Storage
1. Restart bot → verify 004.sql migration applied
2. Send messages → verify `message_embeddings` rows created
3. `!summary clear` + `!summary create` → verify `topics` and
   `topic_messages` rows created
4. Query: `SELECT COUNT(*) FROM topics` — expect 10-15
5. Query: `SELECT COUNT(*) FROM message_embeddings` — expect ~540
6. Query: `SELECT COUNT(*) FROM topic_messages` — expect 200-300
7. Spot-check: `SELECT m.content FROM messages m JOIN topic_messages
   tm ON m.id = tm.message_id WHERE tm.topic_id =
   'topic-database-decision' LIMIT 5` — should be database-related

### Phase 2 — Retrieval Quality
8. Ask about databases → check logs for retrieved topics (should
   include "Database Hosting Decision", not "Bachelor Party Toasts")
9. Ask about animals → check logs for retrieved topics (should
   include "Animal Evolution and Intelligence")
10. Ask a generic greeting → check that retrieval returns minimal/no
    topics (falls back to always-on context only)

### Phase 3 — Budget and Performance
11. Check response latency — should be <300ms slower than before
12. Check token usage — retrieved context should be smaller than
    full summary injection for focused questions
13. Verify recent messages not duplicated in retrieved context

### Phase 4 — Backfill
14. Run `!debug backfill_embeddings` on existing database
15. Verify all non-noise messages have embeddings
16. Verify topics from existing summary have embeddings and linkages

## Implementation Sequence

Recommended build order for Claude Code:

1. `schema/004.sql` — create tables (smallest, no dependencies)
2. `utils/embedding_store.py` — embedding utilities (self-contained)
   Include: embed_text, pack/unpack, cosine_similarity, store ops,
   link_topic_to_messages (embedding similarity linkage)
3. `config.py` — add new env vars
4. `utils/raw_events.py` — embed on message arrival
5. `utils/summarizer_authoring.py` — store topics + link after pipeline
6. `utils/summary_display.py` — always-on context formatter
7. `utils/context_manager.py` — semantic retrieval (the big change)
8. `commands/debug_commands.py` — backfill command
9. Backfill existing data, test, validate

## Future Work

- **Embedding-based message retrieval**: If topic-level retrieval
  is too coarse, add direct message-to-message similarity search
  using `message_embeddings`. Infrastructure already in place.
- **Topic-centric schema**: Decisions, facts, action items nest
  under parent topics via `topic_id` foreign key. Better for both
  retrieval and display. Deferred to avoid schema complexity.
- **Cached query embeddings**: Cache last N user message embeddings
  to avoid re-embedding on rapid follow-up questions.
- **Similarity threshold**: Drop retrieved topics below cosine
  similarity threshold (e.g., 0.3) to avoid injecting marginal
  content.
- **Incremental topic linkage**: When new messages arrive between
  summarization runs, their embeddings are stored but not linked
  to topics. Re-linking happens on the next `!summary create`.
  If needed, a background task could periodically re-link.
