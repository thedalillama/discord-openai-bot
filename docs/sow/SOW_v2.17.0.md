# SOW v2.17.0 — History Trim After Load

**Status**: ✅ Completed  
**Branch**: development  
**Files Changed**: See table below

## Problem Statement
The bot fetches full channel history from Discord (introduced in v2.15.0) so the
settings parser can find confirmed settings anywhere in history. However, after
loading is complete and settings are applied, the full history remains in memory
indefinitely. prepare_messages_for_api() then sends the entire stored history to
the AI provider on every call, resulting in unbounded context size, unnecessary
token costs, and unpredictable API behavior.

## Objective
Trim channel_history to MAX_HISTORY messages immediately after the load pipeline
completes — after settings are parsed and applied, after noise filtering is done.
Once trimmed, prepare_messages_for_api() can send all stored messages directly
with no slicing needed.

## Design Decision
The trim belongs in cleanup_coordinator.py as a new Step 2 in
coordinate_final_cleanup(), between filtering and final validation. This is the
correct location because:
- Settings have already been parsed and applied to memory by this point
- Noise filtering has already run, so we trim clean messages only
- It runs once at load time, keeping memory bounded going forward
- prepare_messages_for_api() stays simple — no runtime slicing needed

## Scope
- cleanup_coordinator.py — add _trim_to_max_history() step after filtering
- No changes to prepare_messages_for_api() in message_processing.py
- No changes to any other files

## Files Modified

| File | Previous Version | New Version | Action |
|------|-----------------|-------------|--------|
| `utils/history/cleanup_coordinator.py` | 2.1.0 | 2.2.0 | Modified |
| `docs/sow/SOW_v2.17.0.md` | — | new | Created |
| `STATUS.md` | 2.16.0 | 2.17.0 | Modified |

## Risk Assessment
Low risk. The trim uses the same [-MAX_HISTORY:] slice pattern already used
elsewhere in the codebase. Settings are fully applied before trim runs so no
settings data is lost. The only behavioral change is reduced memory usage and
bounded API context size.

## Testing
1. Set MAX_HISTORY=10 (or confirm current setting)
2. Ensure channel has more than MAX_HISTORY messages
3. Restart the bot service
4. Verify startup logs show trim step: "Trimmed channel ... history: N → 10 messages"
5. Send a message and verify API call contains no more than MAX_HISTORY messages
6. Verify settings are correctly restored after restart
7. Verify bot responds correctly to messages

## Outcome
channel_history is trimmed to MAX_HISTORY after every load. API context is always
bounded. Memory usage is predictable. Settings persistence is unaffected.
