# SOW v2.20.0 — DeepSeek Reasoning Content Display

## Problem Statement
Three related issues identified with DeepSeek reasoning model support:

1. **Wrong reasoning format**: The bot's thinking display was designed for
   `<think>` tag models. DeepSeek's official API returns reasoning in a
   separate `reasoning_content` field on the message object. As a result
   `!thinking on` has no effect — reasoning content is silently discarded.

2. **Dead code**: `filter_thinking_tags()` and all `<think>` tag logic in
   thinking_commands.py is irrelevant for the DeepSeek official API and
   will never be triggered in the current architecture.

3. **Executor wrapper verified**: `deepseek-reasoner` generates up to 32K
   tokens of reasoning before answering, causing long API call times.
   The existing `run_in_executor()` / `ThreadPoolExecutor` pattern in
   openai_compatible_provider.py v1.0.0 was verified correct — no changes
   needed to the executor wrapper itself.

## Objective
- Correctly extract and display `reasoning_content` from DeepSeek API
- Filter reasoning from channel_history and API payload via noise prefix
- Remove dead `<think>` tag logic

## Design

### Reasoning prefix
All reasoning content sent to Discord is prefixed with:
```
[DEEPSEEK_REASONING]:
```
This prefix is unique enough to never appear in normal conversation.
Added to `is_history_output()` as a noise pattern so reasoning messages
are filtered from channel_history at runtime, load time, and API payload
build. Follows the same proven pattern as API_ERROR_PREFIX.

### `!thinking on` behavior
1. Full `reasoning_content` sent to Discord as a separate message:
```
   [DEEPSEEK_REASONING]:
   {full reasoning_content}
```
   Split across multiple Discord messages if needed via split_message().
2. Answer sent as a separate follow-up message (normal behavior)
3. Full reasoning_content logged at INFO
4. Reasoning message filtered from channel_history (noise prefix)
5. Answer stored in channel_history normally

### `!thinking off` behavior
1. Answer only sent to Discord (normal behavior)
2. reasoning_content logged at DEBUG only
3. Nothing extra stored in channel_history

### Return value from provider
openai_compatible_provider.py always returns a plain string.

When `reasoning_content` present and thinking enabled:
```
[DEEPSEEK_REASONING]:\n{full reasoning_content}\n\n{content}
```

When thinking disabled or no `reasoning_content`:
```
{content}
```

response_handler.py detects the `[DEEPSEEK_REASONING]:` prefix, splits
on `\n\n` after the reasoning block, and sends two separate Discord
messages — reasoning first, answer second. Only the answer is passed
to `add_response_to_history()`.

### Executor wrapper
The existing `run_in_executor()` / `ThreadPoolExecutor` pattern in
openai_compatible_provider.py v1.0.0 was verified correct and covers
the full API call including reasoning token generation. No changes needed.

### `<think>` tag logic removal
`filter_thinking_tags()` and `import re` removed from thinking_commands.py.
`get_thinking_enabled()` and `set_thinking_enabled()` retained — still
used by openai_compatible_provider.py and realtime_settings_parser.py.

### channel_history filtering
`[DEEPSEEK_REASONING]:` added to `is_history_output()` in
message_processing.py. Catches reasoning messages at:
1. Runtime — add_response_to_history() in response_handler.py
2. Load time — discord_converter.py at startup
3. API payload — prepare_messages_for_api() safety net

### Logging
- `!thinking on`: full `reasoning_content` logged at INFO every response
- `!thinking off`: `reasoning_content` logged at DEBUG only

## Files Modified

| File | Previous Version | New Version | Action |
|------|-----------------|-------------|--------|
| `ai_providers/openai_compatible_provider.py` | 1.0.0 | 1.1.0 | Modified |
| `utils/response_handler.py` | 1.1.1 | 1.1.2 | Modified |
| `utils/history/message_processing.py` | 2.2.5 | 2.2.6 | Modified |
| `commands/thinking_commands.py` | 2.0.0 | 2.1.0 | Modified |
| `utils/ai_utils.py` | unversioned | 1.0.0 | Version header added |
| `docs/sow/SOW_v2.20.0.md` | — | new | Created |
| `STATUS.md` | 2.19.0 | 2.20.0 | Modified |

## Risk Assessment
Low. Key risks and mitigations:

1. **Response splitting** — reasoning/answer split in response_handler.py
   uses `[DEEPSEEK_REASONING]:` prefix and `\n\n` separator as reliable
   split point.

2. **Removal of filter_thinking_tags()** — confirmed dead code for DeepSeek
   official API. No other callers in codebase.

## Testing
Phase 1 — with deepseek-chat (no reasoning_content):
1. Address bot — confirm normal response, no reasoning message
2. `!thinking on` — address bot — confirm normal response, no change
3. Check logs — confirm no DEEPSEEK_REASONING entries
4. `!history` — confirm history clean

Phase 2 — switch to deepseek-reasoner in .env, restart:
5. `!thinking off` — address bot with math/logic question
6. Confirm answer only in Discord, no reasoning message
7. Check logs — confirm reasoning logged at DEBUG:
   `sudo journalctl -u discord-bot -n 100 | grep -i "thinking display disabled"`
8. `!thinking on` — address bot with math/logic question
9. Confirm reasoning message appears before answer in Discord
10. Confirm two separate Discord messages
11. Check logs — confirm reasoning logged at INFO:
    `sudo journalctl -u discord-bot -n 100 | grep "DEEPSEEK_REASONING"`
12. `!history` — confirm reasoning NOT in history
13. Check API context logs — confirm reasoning absent from payload
14. Monitor for heartbeat warnings — confirm no blocking:
    `sudo journalctl -u discord-bot -f`

Phase 3 — other providers:
15. `!ai openai` — address bot — confirm normal behavior
16. `!ai anthropic` — address bot — confirm normal behavior
17. Restart — confirm thinking setting restored correctly

## Out of Scope
- Anthropic thinking blocks
- OpenAI reasoning summaries
- Token budget / reasoning effort control
- Long final answer chunking/pagination
