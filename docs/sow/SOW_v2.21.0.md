# SOW v2.21.0 — Async Executor Safety

## Problem Statement

Two related async safety issues identified:

1. **Anthropic provider missing executor wrapper**: `anthropic_provider.py`
   makes a synchronous `self.client.messages.create()` call directly in an
   async method with no `run_in_executor()` wrapper. This blocks the Discord
   event loop for the duration of the API call, risking heartbeat failures
   and WebSocket disconnection — the same crash pattern confirmed in
   production during v2.20.0 development with deepseek-reasoner.

2. **No warning comment on existing executor wrappers**: The critical
   executor wrapper in `openai_compatible_provider.py` has no comment
   explaining why it must not be removed. A developer refactoring the file
   could inadvertently remove it, reintroducing the heartbeat blocking bug.

## Objective

- Add `run_in_executor()` wrapper to `anthropic_provider.py`
- Add critical warning comment to executor wrapper in
  `openai_compatible_provider.py`
- Ensure all three providers follow the same async safety pattern

## Design

### Executor wrapper pattern (established in v2.10.1)
All synchronous API calls must be wrapped as follows:
```python
loop = asyncio.get_event_loop()
with concurrent.futures.ThreadPoolExecutor() as executor:
    response = await loop.run_in_executor(
        executor,
        lambda: self.client.some_api_call(...)
    )
```

### Warning comment (to be added at each executor block)
```python
# CRITICAL: Do NOT remove this executor wrapper.
# Synchronous API calls block the Discord event loop, causing heartbeat
# failures, WebSocket disconnection, and bot crashes under slow or large
# responses. Confirmed via production crash during v2.20.0 development.
# See HANDOFF.md for details.
```

### anthropic_provider.py changes
- Add `import asyncio` and `import concurrent.futures`
- Wrap `self.client.messages.create()` in `run_in_executor()`
- Add critical warning comment
- Add version header: unversioned → v1.0.0

### openai_compatible_provider.py changes
- Add critical warning comment to existing executor block
- Version: 1.1.1 → 1.1.2

## Files to Modify

| File | Current Version | New Version | Action |
|------|----------------|-------------|--------|
| `ai_providers/anthropic_provider.py` | unversioned | 1.0.0 | Modified |
| `ai_providers/openai_compatible_provider.py` | 1.1.1 | 1.1.2 | Modified |
| `docs/sow/SOW_v2.21.0.md` | — | new | Created |
| `STATUS.md` | 2.20.0 | 2.21.0 | Modified |
| `HANDOFF.md` | 2.20.0 | 2.21.0 | Modified |

## Risk Assessment
Low. The executor wrapper pattern is proven and already in use in both
`openai_provider.py` and `openai_compatible_provider.py`. The Anthropic
API call signature does not change — only the async wrapping changes.
The warning comment in openai_compatible_provider.py is documentation
only, no functional change.

## Testing
1. `!ai anthropic` — address bot — confirm normal response
2. Check logs — confirm no heartbeat warnings during Anthropic response
3. `!ai deepseek` — address bot — confirm normal response unaffected
4. `!ai openai` — address bot — confirm normal response unaffected
5. Restart — confirm all providers still functional
