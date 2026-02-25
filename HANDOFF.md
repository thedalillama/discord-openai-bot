# HANDOFF.md
# Version 2.22.0
# Agent Development Handoff Document

## Current Status

**Branch**: development (ahead of main — v2.20.0 through v2.22.0 not yet merged)
**Bot**: Running on systemd, stable, using deepseek-reasoner model
**Last completed**: v2.22.0 — Provider Singleton Caching

---

## Recent Completed Work

### v2.22.0 — Provider Singleton Caching
- **FIXED**: get_provider() was creating a new provider instance on every
  API call — new httpx client each time, causing garbage collection
  RuntimeError when previous instance destroyed mid-request
- **ADDED**: Module-level _provider_cache dictionary in __init__.py
- **BEHAVIOR**: Each provider type instantiated once on first use, reused
  for all subsequent calls for the lifetime of the bot
- **VERIFIED**: Exactly one "Instantiating" log entry per provider type
  per session regardless of message volume
- **File**: ai_providers/__init__.py → v1.3.0

### v2.21.0 — Async Executor Safety
- **FIXED**: Anthropic provider was making synchronous API calls directly
  in async method — heartbeat blocking risk
- **ADDED**: run_in_executor() wrapper to anthropic_provider.py
- **ADDED**: Critical warning comments on all executor blocks
- **Files**: anthropic_provider.py → v1.0.0,
  openai_compatible_provider.py → v1.1.2

### v2.20.0 — DeepSeek Reasoning Content Display
- **FIXED**: DeepSeek reasoner reasoning_content now correctly extracted
  and displayed — was previously silently discarded
- **REMOVED**: Dead filter_thinking_tags() / <think> tag logic
- **BEHAVIOR**: !thinking on — reasoning shown in Discord before answer,
  logged at INFO. !thinking off — answer only, reasoning at DEBUG
- **NOISE FILTERING**: [DEEPSEEK_REASONING]: prefix filters reasoning
  from channel_history at all three layers
- **SPLIT**: Uses [DEEPSEEK_ANSWER]: separator — handles multi-paragraph
  reasoning without false splits on blank lines
- **Files**: openai_compatible_provider.py → v1.1.1, response_handler.py
  → v1.1.3, message_processing.py → v2.2.6, thinking_commands.py → v2.1.0,
  ai_utils.py → v1.0.0

---

## Pending Items

### 1. Merge development → main (IMMEDIATE)
v2.20.0 through v2.22.0 are tested and stable on development branch.
Awaiting user decision to merge to main and tag.

### 2. Token-Based Context Trimming (MEDIUM PRIORITY)
**Issue**: MAX_HISTORY limits message count but not token count. Long messages
can cause context window overflow on API calls.
**Fix**: Token estimation before API calls, trim to MAX_CONTEXT_TOKENS budget
**Design**: Discussed but not yet SOW'd

### 3. README.md Pricing Table (LOW PRIORITY)
**Issue**: OpenAI and Anthropic pricing figures are stale
**Fix**: Update with current API pricing from provider docs

---

## Architecture Notes

### Provider Singleton Pattern
```python
# ai_providers/__init__.py
_provider_cache = {}  # module-level, lives for bot lifetime

def get_provider(provider_name=None, channel_id=None):
    ...
    if provider_name not in _provider_cache:
        _provider_cache[provider_name] = XProvider()  # instantiate once
    return _provider_cache[provider_name]             # reuse always
```

Providers are stateless between calls — all instance variables are
configuration only (model, API key, base URL, max_tokens), set once
in __init__() and never mutated. Safe to reuse across all calls.

### Async Safety Pattern (All Three Providers)
```python
# CRITICAL: Do NOT remove this executor wrapper.
# Synchronous API calls block the Discord event loop, causing heartbeat
# failures, WebSocket disconnection, and bot crashes under slow or large
# responses. Confirmed via production crash during v2.20.0 development.
loop = asyncio.get_event_loop()
with concurrent.futures.ThreadPoolExecutor() as executor:
    response = await loop.run_in_executor(
        executor,
        lambda: self.client.some_api_call(...)
    )
```

### Noise Filtering Architecture (Three Layers)
```
Layer 1 — Runtime:   add_response_to_history() checks is_history_output()
Layer 2 — Load time: discord_converter.py checks is_history_output()
Layer 3 — API build: prepare_messages_for_api() checks is_history_output()
                     AND is_settings_persistence_message()
```

### DeepSeek Reasoning Architecture
```
openai_compatible_provider.py:
  reasoning_content + thinking on:
    → "[DEEPSEEK_REASONING]:\n{reasoning}\n[DEEPSEEK_ANSWER]:\n{answer}"
  reasoning_content + thinking off:
    → "{answer}" only, reasoning logged at DEBUG
  no reasoning_content:
    → "{answer}" normally

response_handler.py:
  detects REASONING_PREFIX → splits on REASONING_SEPARATOR
  → sends reasoning as separate Discord message(s) (not stored)
  → sends answer as separate Discord message(s) (stored normally)
```

### Constants That Must Stay in Sync

| Constant | Files |
|----------|-------|
| `API_ERROR_PREFIX` | response_handler.py, message_processing.py |
| `REASONING_PREFIX` | openai_compatible_provider.py, response_handler.py, message_processing.py |
| `REASONING_SEPARATOR` | openai_compatible_provider.py, response_handler.py |

### Settings Persistence Message Strings
Exact strings required by realtime_settings_parser.py:
- `"Auto-response is now **enabled**"`
- `"Auto-response is now **disabled**"`
- `"AI provider for #channel changed from ... to"`
- `"AI provider for #channel reset from ... to"`
- `"DeepSeek thinking display **enabled**"`
- `"DeepSeek thinking display **disabled**"`

---

## Current .env Configuration
```
AI_PROVIDER=deepseek
OPENAI_COMPATIBLE_API_KEY=sk-[key]
OPENAI_COMPATIBLE_BASE_URL=https://api.deepseek.com
OPENAI_COMPATIBLE_MODEL=deepseek-reasoner
OPENAI_COMPATIBLE_CONTEXT_LENGTH=128000
OPENAI_COMPATIBLE_MAX_TOKENS=8000
```

Switch to `deepseek-chat` for faster/cheaper responses when reasoning
display is not needed.

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
