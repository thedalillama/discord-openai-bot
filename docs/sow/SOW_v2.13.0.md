# SOW v2.13.0 — Command Interface Redesign

**Status**: ✅ Completed  
**Branch**: development → main  
**Files Changed**: All files in `commands/`, `commands/__init__.py`

## Problem Statement
The bot had 15 separate commands with inconsistent naming, duplicate functionality,
and a broken permission model where read operations incorrectly required admin
privileges.

## Objective
Consolidate 15 commands into 6 unified base commands following consistent design
patterns. Fix the permission model so read operations are open to all users while
write operations remain admin-only.

## Scope
- `!prompt` replaces `!setprompt`, `!getprompt`, `!resetprompt`
- `!ai` replaces `!setai`, `!getai`, `!resetai`
- `!autorespond` replaces `!autostatus`, `!autosetup`
- `!thinking` replaces `!thinkingstatus`
- `!history` merges `!cleanhistory` and `!loadhistory` as subcommands
- Fix read/write permission model across all commands
- All commands follow unified Pattern A (toggle) or Pattern B (value) design

## Risk
Medium. High surface area change touching all command modules. Mitigated by
maintaining all underlying logic and only changing the interface layer.

## Outcome
15 commands consolidated into 6. Consistent permission model enforced.
Intuitive command interface delivered.
