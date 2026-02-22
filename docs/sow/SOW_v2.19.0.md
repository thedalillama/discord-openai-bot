# SOW v2.19.0 — Runtime History Noise Filtering

**Status**: ✅ Completed  
**Branch**: development  
**Files Changed**: See table below

## Problem Statement
Bot-generated messages added to channel_history were not filtered before storage
in two separate paths:

1. **Runtime path**: Bot responses stored via response_handler.py without
   checking is_history_output() — command confirmations and error messages
   entered channel_history at runtime
2. **Load-time path**: discord_converter.py added all bot messages to
   channel_history unconditionally — noise messages loaded from Discord history
   on startup entered channel_history without filtering

Both paths caused noise (command confirmations, error messages, settings
persistence messages) to appear in the API context sent to the AI provider.

## Objective
Filter noise from all paths so the API payload only ever contains legitimate
conversation content — real AI responses and user messages.

## Design Decision
Four changes work together:

1. **response_handler.py** — add_response_to_history() checks is_history_output()
   before storing runtime bot responses. Error messages use API_ERROR_PREFIX and
   are never stored.

2. **message_processing.py** — is_history_output() adds API_ERROR_PREFIX pattern
   so error messages are caught at load time. New is_settings_persistence_message()
   identifies admin messages that must stay in channel_history for the settings
   parser but are excluded from the API payload in prepare_messages_for_api().

3. **discord_converter.py** — convert_discord_messages() checks is_history_output()
   before storing bot messages loaded from Discord history. Settings persistence
   messages pass through unaffected since they are not matched by is_history_output().

4. **prepare_messages_for_api()** — filters both is_history_output() and
   is_settings_persistence_message() when building the API payload, so settings
   persistence messages never reach the AI even though they stay in channel_history.

API_ERROR_PREFIX is defined in both response_handler.py and message_processing.py
and must be kept in sync.

## Files Modified

| File | Previous Version | New Version | Action |
|------|-----------------|-------------|--------|
| `utils/response_handler.py` | 1.0.0 | 1.1.1 | Modified |
| `utils/history/message_processing.py` | 2.2.3 | 2.2.5 | Modified |
| `utils/history/discord_converter.py` | 1.0.0 | 1.0.1 | Modified |
| `docs/sow/SOW_v2.19.0.md` | — | new | Created |
| `STATUS.md` | 2.18.0 | 2.19.0 | Modified |

## Risk Assessment
Low. The filter logic is well-tested. Settings persistence messages are
explicitly protected in channel_history and only excluded from the API payload.
The only behavioral change is that noise messages are excluded from the API
context in all paths.

## Testing
1. Trigger a provider error — confirm error message appears in Discord with
   standard prefix but NOT in !history output or API context logs
2. Run !autorespond off — confirm confirmation does NOT appear in API context logs
3. Switch providers with !ai — confirm "AI provider changed from" does NOT appear
   in API context logs
4. Restart bot — confirm settings (provider, prompt, autorespond) correctly
   restored after restart, confirming settings persistence still works
5. Verify normal AI responses ARE stored correctly in history

## Outcome
channel_history is clean in the runtime path, the load-time path, and the API
payload path. Settings persistence messages stay in channel_history for the
parser but never reach the AI. API context contains only legitimate conversation
content.
