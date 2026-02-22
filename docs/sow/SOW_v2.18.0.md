# SOW v2.18.0 — Continuous Context Accumulation

**Status**: ✅ Completed  
**Branch**: development  
**Files Changed**: See table below

## Problem Statement
When auto-respond is disabled, regular conversational messages between users were
not added to channel_history. When the bot was later addressed directly, it had no
awareness of the conversation that occurred since the last history load. Context
was lost during any period when auto-respond was off.

## Objective
Ensure all non-command user messages are appended to channel_history regardless
of whether auto-respond is enabled. The bot should always be listening and
accumulating context, even when not responding.

## Design Decision
The fix is in bot.py on_message(). Regular messages (non-command, non-addressed)
are now unconditionally appended to channel_history before the auto-respond check.
The auto-respond check then determines whether to respond — but history accumulation
always happens regardless.

### Message handling logic after this change:
1. Direct-addressed message → append to history + respond
2. Bot command (!) → skip, do not add to history
3. Regular message, auto-respond ON → append to history + respond
4. Regular message, auto-respond OFF → append to history, do not respond

The in-memory MAX_HISTORY trim runs after every append to keep memory bounded.

## Files Modified

| File | Previous Version | New Version | Action |
|------|-----------------|-------------|--------|
| `bot.py` | 2.8.0 | 2.9.0 | Modified |
| `docs/sow/SOW_v2.18.0.md` | — | new | Created |
| `STATUS.md` | 2.17.0 | 2.18.0 | Modified |

## Risk Assessment
Low. No new code paths for responding. No API calls added. The only behavioral
change is that regular messages are appended to channel_history when auto-respond
is off. The MAX_HISTORY trim ensures memory stays bounded.

## Testing
1. Disable auto-respond in a channel
2. Have a multi-message conversation between users
3. Address the bot directly
4. Verify the bot's response shows awareness of the prior conversation
5. Verify bot does not respond to non-addressed messages when auto-respond is off
6. Verify history length stays bounded to MAX_HISTORY

## Outcome
Bot always accumulates context regardless of auto-respond state. Direct addressing
after a silent period gives the bot full awareness of the intervening conversation.
