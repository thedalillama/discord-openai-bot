# SOW v5.9.0 — Citation-Backed Responses
# Part 2 of 2: Data Flow, Response Handler, Testing
# Status: PROPOSED — awaiting approval
# Branch: claude-code

---

## Data Flow

```
_retrieve_cluster_context()
  → builds context text with [N] labels
  → builds citation_map: {1: {author, date, content, ...}, ...}
  → returns (context_text, tokens_used, cluster_receipt, citation_map)

build_context_for_provider()
  → receives citation_map from retrieval
  → passes through to return value
  → returns (messages, receipt, citation_map)

bot.py on_message()
  → messages, receipt, citation_map = build_context_for_provider(...)
  → await handle_ai_response(message, channel_id, messages,
                              receipt_data=receipt,
                              citation_map=citation_map)

handle_ai_response()
  → response_text = generate_ai_response(messages, ...)
  → if citation_map:
      response_text = strip_hallucinated_citations(response_text,
                                                    citation_map)
      footer = build_citation_footer(response_text, citation_map)
      response_text = response_text + footer
  → send response to Discord
  → store receipt
```

### Return Value Changes

`_retrieve_cluster_context()` currently returns:
```python
(context_text, tokens_used)
```

Changes to:
```python
(context_text, tokens_used, citation_map)
```

`build_context_for_provider()` currently returns:
```python
(messages, receipt)
```

Changes to:
```python
(messages, receipt, citation_map)
```

`handle_ai_response()` currently accepts:
```python
(message, channel_id, messages, receipt_data=None)
```

Changes to:
```python
(message, channel_id, messages, receipt_data=None, citation_map=None)
```

### Callers to Update

Only `bot.py` calls `build_context_for_provider()` — one call site
to update. Only `bot.py` calls `handle_ai_response()` — one call
site.

---

## Discord Message Length Handling

The response + citations may exceed Discord's 2000 char limit.

**Strategy:**
1. If response + full footer < 2000 chars: send as one message
2. If response alone < 2000 chars but footer pushes over: send
   response first, then footer as a follow-up message (prefixed
   with ℹ️ so it's recognized as bot output)
3. If response alone > 2000 chars: use existing pagination, append
   footer to the last page or as a follow-up

The footer should be visually distinct — separated by a blank line
and bold "Sources:" header. It's informational, not part of the
conversational response.

---

## Citation Prompt Tuning

The citation instruction needs to be clear but not overly
prescriptive. LLMs that are over-instructed on citations tend to
cite everything or cite incorrectly. Start with:

```
CITATION INSTRUCTIONS:
The messages below are numbered [1], [2], etc. When your response
uses specific information from these messages, add the citation
number in brackets after the claim. Example: "The database is
PostgreSQL [3]." Only cite when you directly use information from
a specific message. Do not cite for general knowledge or your own
reasoning.
```

If the LLM over-cites (every sentence has [N]), simplify to:
```
Messages are numbered [1], [2], etc. Cite with [N] when using
specific facts from those messages.
```

If the LLM under-cites (never adds [N]), strengthen to:
```
You MUST cite sources using [N] notation when your answer includes
facts from the numbered messages below.
```

This will need tuning per provider. GPT-4o-mini, DeepSeek, and
Anthropic models may respond differently to citation instructions.
Start with the middle-strength version and adjust based on testing.

---

## Testing Plan

### Test 1: Basic Citation
Ask "how strong are gorillas?" — response should include [N]
markers and a Sources footer. Verify cited sources are real
messages about gorilla strength.

### Test 2: No Citations
Say "hi, how are you?" — response should NOT have citations.
No footer.

### Test 3: Multi-Cluster Citation
Ask a question that pulls from multiple clusters, like "compare
gorilla and squirrel strength." Citations should reference messages
from both the gorilla and squirrel clusters.

### Test 4: Hallucination Check
If the LLM cites [15] but only 12 messages were in context,
[15] should be stripped from the response. No phantom sources
in the footer.

### Test 5: Training Knowledge vs Retrieved
Ask about something not discussed in the channel. The bot should
answer from training knowledge with no citations. Then ask about
something that WAS discussed — citations should appear.

### Test 6: Footer Length
Ask a broad question that retrieves many messages. Verify the
footer doesn't exceed Discord limits. If it does, verify the
overflow handling (follow-up message or truncation).

### Test 7: Citation + Explain
Run `!explain` after a cited response. The receipt should still
work correctly. The citation map data could optionally be stored
in the receipt for cross-referencing.

### Test 8: Provider Consistency
Test with GPT-4o-mini, DeepSeek, and any other configured
provider. Each may need citation prompt tuning. Note which
providers over-cite, under-cite, or cite correctly.

---

## Files Changed Summary

| File | Change |
|------|--------|
| `utils/context_retrieval.py` | Add citation labels to retrieved messages, build citation_map, return it |
| `utils/context_manager.py` | Pass citation_map through from retrieval to return value |
| `bot.py` | Unpack citation_map, pass to handle_ai_response |
| `utils/response_handler.py` | Accept citation_map, validate citations, build footer, append to response |
| NEW `utils/citation_utils.py` | build_citation_footer(), strip_hallucinated_citations() — if response_handler would exceed 250 lines |

---

## Documentation Updates

- `STATUS.md` — add v5.9.0 entry
- `HANDOFF.md` — update with citation feature
- `README.md` — add citation feature to description
- `AGENT.md` — update architecture context

---

## Constraints

1. Full files only
2. Increment version numbers
3. 250-line limit per file
4. Citations only when retrieved messages exist
5. Validate all cited numbers against citation_map
6. Strip hallucinated citations before sending
7. Handle Discord 2000 char limit gracefully
8. ℹ️ prefix on follow-up footer messages
9. Citation instructions in the context block, NOT base system prompt
10. asyncio.to_thread() for any new SQLite operations
