# SOW v2.22.0 — Provider Singleton Caching

## Problem Statement

`get_provider()` in `ai_providers/__init__.py` creates a new provider instance
on every API call. Each instantiation creates a new httpx client internally.
When the previous instance is garbage collected while a request is still in
flight, it can trigger a reentrant stdout flush RuntimeError — a known issue
with httpx clients being destroyed mid-operation. Under high message volume
this becomes increasingly likely.

## Objective

Cache provider instances as singletons so each provider type is instantiated
once and reused across all API calls for the lifetime of the bot.

## Design

### Cache dictionary
A module-level dictionary keyed by provider name:

```python
_provider_cache = {}
```

### get_provider() changes
Before instantiating a new provider, check the cache. If not present,
instantiate and cache. If present, return cached instance:

```python
if provider_name not in _provider_cache:
    logger.info(f"Instantiating XProvider (first use)")
    _provider_cache[provider_name] = XProvider()
else:
    logger.debug(f"Returning cached {provider_name} provider instance")
return _provider_cache[provider_name]
```

### Lazy initialization
Providers are instantiated on first use, not at startup. This means:
- deepseek provider instantiated on first deepseek API call
- anthropic provider instantiated on first anthropic API call
- openai provider instantiated on first openai API call

### clear_provider_cache()
Utility function added for testing and future use:

```python
def clear_provider_cache():
    """Clear cached provider instances. Primarily for testing."""
    _provider_cache.clear()
    logger.info("Provider cache cleared")
```

### Thread safety
The executor wrapper in each provider runs API calls in a thread pool, but
`get_provider()` itself is called from the async event loop — single-threaded.
No locking needed.

### Provider statefulness
All provider instance variables are configuration only (model, API key,
base URL, max_tokens) — set once in __init__() and never mutated at runtime.
Reusing the same instance across calls is functionally identical to creating
a new one each time.

## Files Modified

| File | Previous Version | New Version | Action |
|------|-----------------|-------------|--------|
| `ai_providers/__init__.py` | 1.2.0 | 1.3.0 | Modified |
| `docs/sow/SOW_v2.22.0.md` | — | new | Created |
| `STATUS.md` | 2.21.0 | 2.22.0 | Modified |
| `HANDOFF.md` | 2.21.0 | 2.22.0 | Modified |

## Risk Assessment
Low. Providers are stateless between calls — they store no per-request data
on self. The only instance variables are configuration which never changes
at runtime. Reusing the same instance is functionally identical to creating
a new one each time, with the added benefit of a stable httpx client.

## Testing
1. Restart bot — confirm clean startup
2. `!ai deepseek` — address bot — confirm normal response
3. `!ai anthropic` — address bot — confirm normal response
4. `!ai openai` — address bot — confirm normal response
5. Check logs — confirm exactly one instantiation per provider:
   `sudo journalctl -u discord-bot -n 100 | grep -E "Instantiating|Initialized"`
   Expected: three entries total, one per provider type
6. Send several more messages — confirm no additional instantiation entries
7. Restart — confirm providers re-initialize cleanly on startup

## Test Results
- ✅ Exactly three instantiation log entries across full session
- ✅ One per provider type (anthropic, deepseek, openai)
- ✅ No repeated instantiations on subsequent calls
- ✅ All providers return normal responses
