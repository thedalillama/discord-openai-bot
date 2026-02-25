# HANDOFF.md
# Version 2.21.0
# Agent Development Handoff Document

## Current Status

**Branch**: development (ahead of main — v2.20.0 and v2.21.0 not yet merged)
**Bot**: Running on systemd, stable, using deepseek-reasoner model
**Last completed**: v2.21.0 — Async Executor Safety

---

## Recent Completed Work

### v2.21.0 — Async Executor Safety
- **FIXED**: Anthropic provider was making synchronous API calls directly in
  async method — heartbeat blocking risk under slow or large responses
- **ADDED**: run_in_executor() / ThreadPoolExecutor wrapper to anthropic_provider.py
- **ADDED**: Critical warning comments on all executor blocks in all three providers
- **PATTERN**: All providers now consistent — OpenAI, Anthropic, OpenAI-compatible
  all use identical async safety pattern
- **Files**: anthropic_provider.py → v1.0.0,
  openai_compatible_provider.py → v1.1.2

### v2.20.0 — DeepSeek Reasoning Content Display
- **FIXED**: DeepSeek reasoner `reasoning_content` now correctly extracted
  and displayed — was previously silently discarded
- **REMOVED**: Dead `<think>` tag logic (`filter_thinking_tags()`) from
  thinking_commands.py — irrelevant for DeepSeek official API
- **BEHAVIOR**:
  - `!thinking on` — full reasoning shown in Discord as separate message
    before answer, logged at INFO
  - `!thinking off` — answer only in Discord, reasoning logged at DEBUG
- **NOISE FILTERING**: `[DEEPSEEK_REASONING]:` prefix filters reasoning
  from channel_history at runtime, load time, and API payload
- **SPLIT FIX**: Uses `[DEEPSEEK_ANSWER]:` separator (not `\n\n`) to
  reliably split reasoning and answer — handles multi-paragraph reasoning
- **Files**: openai_compatible_provider.py → v1.1.1, response_handler.py
  → v1.1.3, message_processing.py → v2.2.6, thinking_commands.py → v2.1.0,
  ai_utils.py → v1.0.0

### v2.19.0 — Runtime History Noise Filtering
- Bot confirmation messages and error messages filtered from channel_history
  at runtime, load time, and API payload build
- Three-layer filtering: add_response_to_history(), discord_converter.py,
  prepare_messages_for_api()

### v2.18.0 — Continuous Context Accumulation
- Regular messages added to channel_history even when auto-respond disabled

---

## Pending Items

### 1. Merge development → main (IMMEDIATE)
v2.20.0 and v2.21.0 are tested and stable on development branch.
Awaiting user decision to merge to main and tag.

### 2. Provider Singleton Caching (MEDIUM PRIORITY)
**Issue**: get_provider() creates a new provider instance on every API call.
Garbage collected httpx client causes reentrant stdout flush RuntimeError.
**Fix**: Cache provider instances as singletons in ai_providers/__init__.py
**File**: ai_providers/__init__.py

### 3. Token-Based Context Trimming (MEDIUM PRIORITY)
**Issue**: MAX_HISTORY limits message count but not token count. Long messages
can cause context window overflow on API calls.
**Fix**: Token estimation before API calls, trim to MAX_CONTEXT_TOKENS budget
**Design**: Discussed but not yet SOW'd

### 4. README.md Pricing Table (LOW PRIORITY)
**Issue**: OpenAI and Anthropic pricing figures are stale
**Fix**: Update with current API pricing from provider docs

---

## Architecture Notes

### Noise Filtering Architecture (Three Layers)
```
Layer 1 — Runtime:   add_response_to_history() checks is_history_output()
Layer 2 — Load time: discord_converter.py checks is_history_output()
Layer 3 — API build: prepare_messages_for_api() checks is_history_output()
                     AND is_settings_persistence_message()
```

Settings persistence messages (auto-respond, provider change, thinking
display confirmations) stay in channel_history for realtime_settings_parser.py
but are filtered from the API payload at Layer 3.

### DeepSeek Reasoning Architecture
```
openai_compatible_provider.py:
  reasoning_content present + thinking on:
    → returns "[DEEPSEEK_REASONING]:\n{reasoning}\n[DEEPSEEK_ANSWER]:\n{answer}"
  reasoning_content present + thinking off:
    → returns "{answer}" only, reasoning logged at DEBUG
  no reasoning_content:
    → returns "{answer}" normally

response_handler.py:
  detects REASONING_PREFIX → splits on REASONING_SEPARATOR
  → sends reasoning as separate Discord message(s) (not stored in history)
  → sends answer as separate Discord message(s) (stored in history)

message_processing.py:
  is_history_output() catches [DEEPSEEK_REASONING]: prefix
  → filters reasoning from channel_history at all three layers
```

### Constants That Must Stay in Sync
These constants are defined in two places and must match exactly:

| Constant | File 1 | File 2 |
|----------|--------|--------|
| `API_ERROR_PREFIX` | response_handler.py | message_processing.py |
| `REASONING_PREFIX` | openai_compatible_provider.py | response_handler.py + message_processing.py |
| `REASONING_SEPARATOR` | openai_compatible_provider.py | response_handler.py |

### Settings Persistence Message Strings
These exact strings are required by realtime_settings_parser.py and must
not be changed without updating the parser:
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
8. Test in terminal AND service before committing
9. Update STATUS.md and HANDOFF.md with every commit
