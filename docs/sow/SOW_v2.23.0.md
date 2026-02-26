# SOW v2.23.0 — Token-Budget Context Management + Usage Logging

**Status**: 🔨 In Progress
**Branch**: development
**Depends on**: v2.22.0 (provider singleton caching)

## Problem Statement
1. No token awareness — MAX_HISTORY limits message count but a single large
   paste can exceed a provider's context window. `prepare_messages_for_api()`
   includes all messages regardless of total token size.
2. No usage visibility — token consumption per API call is not logged,
   making cost analysis and technique comparison impossible.
3. DeepSeek context default wrong (128K vs actual 64K API limit).
4. Anthropic model default stale (`claude-3-haiku-20240307`).

## Objective
- Guarantee every API call fits within the provider's context window
- Log per-call and cumulative token usage for cost baselining

---

## Part 1: Token Budget (COMPLETE)

### Token Counting
Unified `tiktoken` cl100k_base for all providers. Exact for OpenAI,
near-exact for DeepSeek (~95-99%), approximate for Anthropic (~85-90%).
Fallback: `len(text) / 3.2` if tiktoken unavailable.

### Budget Formula
```
input_budget = (context_window * CONTEXT_BUDGET_PERCENT / 100) - max_output_tokens
```
Default 80%. The 20% headroom exceeds Anthropic's tokenizer variance.

### Core Logic (`build_context_for_provider`)
1. Call `prepare_messages_for_api()` for noise filtering (unchanged)
2. Compute budget from provider limits
3. Always include system prompt
4. Add messages newest-to-oldest until budget exhausted
5. Reverse to chronological, return

### Two Trimming Layers
- **MAX_HISTORY** (bot.py) — coarse memory bound
- **Token budget** (context_manager.py) — precise API safety

### Call Flow
`bot.py → get_provider() → build_context_for_provider() → handle_ai_response()`

---

## Part 2: Token Usage Logging (PENDING)

### Design
Each provider extracts actual token counts from its API response object
and logs them at INFO level. An in-memory accumulator in
`context_manager.py` tracks per-channel running totals.

### Provider Usage Fields

| Provider | API | Input field | Output field |
|----------|-----|------------|-------------|
| DeepSeek | Chat Completions | `usage.prompt_tokens` | `usage.completion_tokens` |
| Anthropic | Messages | `usage.input_tokens` | `usage.output_tokens` |
| OpenAI | Responses | `usage.input_tokens` | `usage.output_tokens` |

### Accumulator (`context_manager.py`)
```python
# Module-level, resets on restart
_channel_usage = defaultdict(lambda: {"input": 0, "output": 0, "calls": 0})

def record_usage(channel_id, provider_name, input_tokens, output_tokens):
    """Record token usage and log. Called by each provider after API call."""

def get_channel_usage(channel_id):
    """Return accumulated usage dict for a channel."""
```

### Per-Call INFO Log
```
Token usage [deepseek] ch:1472003599985934560: 1961 in + 342 out = 2303 total
```

### Cumulative DEBUG Log (after each call)
```
Cumulative [deepseek] ch:1472003599985934560: 24,500 in + 8,200 out (47 calls)
```

### Provider Changes
Each provider adds ~5 lines after the API response to extract usage and
call `record_usage()`. No change to return values or response_handler.

### Error Handling
If `response.usage` is None or missing (some providers omit it on error),
log a DEBUG warning and skip recording. Never fail the response.

---

## Verified Provider Specifications (2025-02-26)

| Provider | Model | Context | Max Output |
|----------|-------|---------|------------|
| OpenAI | gpt-4o-mini | 128K | 16,384 |
| DeepSeek | deepseek-chat | 64K | 8,000 |
| DeepSeek | deepseek-reasoner | 64K | 8K+32K CoT |
| Anthropic | claude-haiku-4-5-20251001 | 200K | 64,000 |

## Files Modified

| File | Old Ver | New Ver | Changes |
|------|---------|---------|---------|
| `utils/context_manager.py` | — | 1.0.0 | Token counting + budget + usage accumulator |
| `bot.py` | 2.9.0 | 2.10.0 | Resolve provider early, call build_context |
| `config.py` | 1.5.0 | 1.6.0 | CONTEXT_BUDGET_PERCENT, DeepSeek 64K, Anthropic model |
| `utils/response_handler.py` | 1.1.3 | 1.1.4 | MAX_HISTORY trim after assistant append |
| `ai_providers/openai_provider.py` | 1.2.0 | 1.3.0 | Extract + log usage |
| `ai_providers/anthropic_provider.py` | 1.0.0 | 1.1.0 | Extract + log usage |
| `ai_providers/openai_compatible_provider.py` | 1.1.2 | 1.2.0 | Extract + log usage |
| `requirements.txt` | — | — | Added tiktoken>=0.5.0 |
| Docs: README, README_ENV, STATUS, HANDOFF | 2.22.0 | 2.23.0 | Updated |

**Unchanged**: message_processing.py, cleanup_coordinator.py, commands/*

## Testing Plan
**Part 1 (budget):** ✅ Complete
1. Normal response at 80% budget — all messages fit
2. Forced trim at 15% budget — 9 messages dropped, INFO logged
3. Provider switching — correct budget per provider
4. tiktoken loaded, accurate counts confirmed

**Part 2 (usage logging):**
1. Address bot, verify INFO log shows input + output tokens
2. Compare provider-reported input tokens vs tiktoken estimate
3. Multiple calls, verify cumulative totals accumulate correctly
4. Switch providers mid-conversation, verify per-provider logging
5. Restart bot, verify totals reset (expected behavior)
6. Error case: verify missing usage doesn't break response

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| tiktoken import failure | Fallback to chars/3.2, WARNING log |
| Budget too aggressive | Returns system prompt only, WARNING log |
| DeepSeek context change | Conservative 64K, env override available |
| response.usage missing | Skip recording, DEBUG log, response unaffected |
| OpenAI Responses API usage format | Verified: uses input_tokens/output_tokens |
