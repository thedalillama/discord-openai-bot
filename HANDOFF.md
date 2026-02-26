# HANDOFF.md
# Version 2.23.0
# Agent Development Handoff Document

## Current Status

**Branch**: development (ahead of main — v2.20.0 through v2.23.0 not yet merged)
**Bot**: Running on systemd, stable, using deepseek-reasoner model
**Last completed**: v2.23.0 — Token-Budget Context Management + Usage Logging

---

## Recent Completed Work

### v2.23.0 — Token-Budget Context Management + Usage Logging
- **ADDED**: `utils/context_manager.py` v1.0.0 — token counting via tiktoken,
  budget-aware context builder, per-channel usage accumulator
- **BUDGET**: `input_budget = (context_window * CONTEXT_BUDGET_PERCENT / 100) - max_output`
  Default 80% — headroom absorbs tiktoken variance for Anthropic (~10-15%)
- **USAGE**: All three providers extract actual token counts from API responses
  and log at INFO level. Cumulative per-channel totals at DEBUG.
- **FIXED**: DeepSeek context length default 128000 → 64000
- **FIXED**: Response handler trims to MAX_HISTORY after assistant append
- **UPDATED**: Anthropic model default to `claude-haiku-4-5-20251001`
- **DEPENDENCY**: Added `tiktoken>=0.5.0` to requirements.txt
- **Files**: bot.py → v2.10.0, config.py → v1.6.0,
  response_handler.py → v1.1.4, context_manager.py → v1.0.0,
  openai_provider.py → v1.3.0, anthropic_provider.py → v1.1.0,
  openai_compatible_provider.py → v1.2.0

### v2.22.0 — Provider Singleton Caching
- **File**: ai_providers/__init__.py → v1.3.0

### v2.21.0 — Async Executor Safety
- **Files**: anthropic_provider.py → v1.0.0, openai_compatible_provider.py → v1.1.2

### v2.20.0 — DeepSeek Reasoning Content Display
- **Files**: openai_compatible_provider.py → v1.1.1, response_handler.py
  → v1.1.3, message_processing.py → v2.2.6, thinking_commands.py → v2.1.0

---

## Pending Items

### 1. Merge development → main (IMMEDIATE)
v2.20.0 through v2.23.0 tested and stable on development branch.

### 2. Rolling Summary / Meeting Minutes (FUTURE — Phase 2)
**Issue**: Long conversations lose older context when token budget trims
**Injection point**: `build_context_for_provider()` — summary after system
prompt, before conversation messages, consuming part of token budget
**Baseline**: Token usage logs from v2.23.0 provide cost comparison data
**Design**: Not yet SOW'd

---

## Architecture Notes

### Token Budget + Usage Architecture (v2.23.0)
```
bot.py:
  → get_provider(provider_override, channel_id)
  → build_context_for_provider(channel_id, provider)  # budget trim
  → handle_ai_response(message, channel_id, messages)

Each provider after API call:
  → record_usage(channel_id, name, input_tokens, output_tokens)
  → INFO log: "Token usage [deepseek] ch:123: 1961 in + 342 out = 2303"
  → DEBUG log: "Cumulative [deepseek] ch:123: 24500 in + 8200 out (47 calls)"
```

Two trimming layers:
- **MAX_HISTORY** (message count) — coarse memory bound in bot.py
- **Token budget** (token count) — precise API safety in context_manager.py

Usage accumulator: `_channel_usage` dict in context_manager.py, resets on
restart. Providers write via `record_usage()`, read via `get_channel_usage()`.

### Provider Usage Field Mapping

| Provider | API | Input field | Output field |
|----------|-----|------------|-------------|
| DeepSeek | Chat Completions | `usage.prompt_tokens` | `usage.completion_tokens` |
| Anthropic | Messages | `usage.input_tokens` | `usage.output_tokens` |
| OpenAI | Responses | `usage.input_tokens` | `usage.output_tokens` |

### Provider Singleton Pattern
```python
_provider_cache = {}
def get_provider(provider_name=None, channel_id=None):
    if provider_name not in _provider_cache:
        _provider_cache[provider_name] = XProvider()
    return _provider_cache[provider_name]
```

### Async Safety Pattern (All Three Providers)
```python
# CRITICAL: Do NOT remove this executor wrapper.
loop = asyncio.get_event_loop()
with concurrent.futures.ThreadPoolExecutor() as executor:
    response = await loop.run_in_executor(executor, lambda: ...)
```

### Noise Filtering Architecture (Three Layers)
```
Layer 1 — Runtime:   add_response_to_history() checks is_history_output()
Layer 2 — Load time: discord_converter.py checks is_history_output()
Layer 3 — API build: prepare_messages_for_api() checks is_history_output()
                     AND is_settings_persistence_message()
```

### Constants That Must Stay in Sync

| Constant | Files |
|----------|-------|
| `API_ERROR_PREFIX` | response_handler.py, message_processing.py |
| `REASONING_PREFIX` | openai_compatible_provider.py, response_handler.py, message_processing.py |
| `REASONING_SEPARATOR` | openai_compatible_provider.py, response_handler.py |

### Verified Provider Specifications (2025-02-26)

| Provider | Model | Context Window | Max Output |
|----------|-------|---------------|------------|
| OpenAI | gpt-4o-mini | 128,000 | 16,384 |
| DeepSeek | deepseek-chat | 64,000 | 8,000 |
| DeepSeek | deepseek-reasoner | 64,000 | 8,000 (+32K CoT) |
| Anthropic | claude-haiku-4-5-20251001 | 200,000 | 64,000 |

---

## Current .env Configuration
```
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=sk-[key]
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-reasoner
OPENAI_COMPATIBLE_CONTEXT_LENGTH=64000
OPENAI_COMPATIBLE_MAX_TOKENS=8000
```

---

## Development Rules (from AGENT.md)
1. NO CODE CHANGES WITHOUT APPROVAL
2. ALL DEVELOPMENT WORK IN development BRANCH
3. main BRANCH IS FOR STABLE CODE ONLY
4. DISCUSS FIRST, CODE SECOND
5. ALWAYS provide full files — no partial patches
6. INCREMENT version numbers in file heading comments
7. Keep files under 250 lines
8. Test before committing
9. Update STATUS.md and HANDOFF.md with every commit
