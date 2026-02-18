# SOW v2.14.0 — History Noise Cleanup

**Status**: ✅ Completed  
**Branch**: development → main  
**Files Changed**: `utils/history/message_processing.py` → v2.2.3, `commands/history_commands.py` → v2.0.1, `utils/history/cleanup_coordinator.py` → v2.1.0

## Problem Statement
Bot command responses and housekeeping messages (e.g. `!status` output, permission
denied responses, options lines) were being sent to the AI API as part of conversation
context, polluting the AI's understanding of the conversation.

## Objective
Ensure only real user and AI messages are included in the context sent to the AI API.
Expand `is_history_output()` filtering patterns to catch all v2.13.0 command outputs,
and unify manual `!history reload` to run the same full clean pass as startup reload.

## Scope
- Expand `is_history_output()` patterns in `message_processing.py`
- Update `cleanup_coordinator.py` to filter assistant-side noise during reload
- Update `history_commands.py` so `!history reload` runs full clean pass
- No changes to command interfaces or user-facing behavior

## Risk
Low. Purely additive filter patterns; no existing functionality removed.

## Outcome
Clean conversation context confirmed sent to AI. Bot housekeeping messages
fully excluded from AI API context.
