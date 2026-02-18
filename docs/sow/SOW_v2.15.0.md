# SOW v2.15.0 — Settings Persistence Fix

**Status**: ✅ Completed  
**Branch**: development  
**Files Changed**: `utils/history/discord_fetcher.py` → v1.1.0, `STATUS.md` → v2.15.0

## Problem Statement
The settings persistence feature was broken because `discord_fetcher.py` fetched
only `INITIAL_HISTORY_LOAD` (50) messages from Discord. Since settings parsing
happens against this limited fetch, any settings confirmed more than 50 messages
back in channel history were never seen and therefore never restored after a bot
restart.

## Objective
Remove the `INITIAL_HISTORY_LOAD` cap from the initial message fetch so all
channel messages are retrieved, allowing the existing settings parser to scan
full history and correctly restore the most recent settings for each setting type.

## Scope
- Modify `fetch_messages_from_discord()` in `discord_fetcher.py` to use `limit=None`
- Update log messages that referenced `INITIAL_HISTORY_LOAD` in that function
- `fetch_recent_messages()` retains its limit behavior (lightweight utility)
- No changes to `realtime_settings_parser.py`, `discord_loader.py`, or `config.py`

## Risk
Low. The existing pipeline already handled large message sets correctly. Only
performance consideration is longer load times on channels with very long histories.

## Testing
1. Set AI provider to non-default in a channel
2. Send more than 50 messages after the provider change
3. Restart the bot
4. Verify the provider setting is correctly restored

## Outcome
Settings persistence confirmed working. All channel settings correctly restored
after bot restart regardless of channel history length.
