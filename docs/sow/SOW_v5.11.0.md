# SOW v5.11.0 — History Package Consolidation
# Status: PROPOSED — awaiting approval
# Branch: claude-code
# Prerequisite: v5.10.1 merged into development

---

## Objective

Remove indirection layers and dead code from `utils/history/`. The
package currently has 3 files that exist only as import/export
passthrough layers (`api_imports.py`, `api_exports.py`, `loading.py`)
and 1 file with zero external callers (`management_utilities.py`).
This consolidation eliminates the indirection, inlines imports into
`__init__.py`, and removes dead code.

---

## Scope

### Delete 4 files

| File | Why |
|------|-----|
| `utils/history/api_imports.py` v1.3.0 | Pure import passthrough — re-imports from 8 sibling modules and re-exports via wildcard. Only caller is `__init__.py`. |
| `utils/history/api_exports.py` v1.3.0 | Pure `__all__` definition — only consumed by `__init__.py`. |
| `utils/history/management_utilities.py` v1.0.0 | 5 functions extracted from `settings_manager.py` for 250-line compliance. 4 functions (`clear_channel_settings`, `get_settings_statistics`, `get_channel_setting_summary`, `bulk_clear_settings`) have zero external callers — dead code. 1 function (`validate_setting_value`) is actively imported by `settings_manager.py` — must be inlined back into `settings_manager.py` before deletion. |
| `utils/history/loading.py` v2.5.0 | 40-line passthrough — `load_channel_history()` delegates to `channel_coordinator.py`, utility functions delegate to `loading_utils.py`. Merge `load_channel_history()` into `channel_coordinator.py`; re-export utilities directly from `__init__.py`. |

### Modify 3 files

**`utils/history/__init__.py`** — Replace `from .api_imports import *`
and `from .api_exports import __all__` with direct imports from the
actual source modules. Define `__all__` inline. Remove management
utilities exports. Remove loading.py imports (replaced by direct
imports from channel_coordinator and loading_utils).

The new `__init__.py` should import only what external code actually
uses, plus what internal modules need for backward compatibility.
The active imports are:

From `storage.py`: `channel_history`, `loaded_history_channels`,
`channel_locks`, `channel_system_prompts`, `channel_ai_providers`,
`get_or_create_channel_lock`, `is_channel_history_loaded`,
`mark_channel_history_loaded`, `get_channel_history`,
`add_message_to_history`, `trim_channel_history`,
`clear_channel_history`, `filter_channel_history`

From `message_processing.py`: `is_bot_command`, `is_history_output`,
`should_skip_message_from_history`, `create_user_message`,
`create_assistant_message`, `create_system_update_message`,
`prepare_messages_for_api`, `extract_system_prompt_updates`

From `prompts.py`: `get_system_prompt`, `set_system_prompt`,
`get_ai_provider`, `set_ai_provider`, `remove_ai_provider`,
`remove_system_prompt`

From `channel_coordinator.py`: `load_channel_history`

From `loading_utils.py`: `get_loading_status`,
`force_reload_channel_history`, `get_history_statistics`

From `discord_fetcher.py`: `fetch_messages_from_discord`

From `discord_converter.py`: `convert_discord_messages`,
`count_convertible_messages`, `filter_messages_for_conversion`,
`validate_discord_message`, `extract_message_metadata`

From `realtime_settings_parser.py`: `parse_settings_during_load`,
`extract_prompt_from_update_message` (as `..._new`)

From `discord_loader.py`: `load_messages_from_discord`,
`process_discord_messages`, `extract_prompt_from_update_message`,
`count_processable_messages`

From `settings_manager.py`: `apply_restored_settings`,
`validate_parsed_settings`, `get_restoration_summary`,
`apply_individual_setting`

**`utils/history/channel_coordinator.py`** — Add
`load_channel_history()` function (moved from `loading.py`). This is
a thin wrapper that calls `coordinate_channel_loading()` — keeping it
as a named public API entry point so `from utils.history import
load_channel_history` continues to work.

**`utils/history/settings_manager.py`** — Inline
`validate_setting_value()` from `management_utilities.py`. This
function is actively called during settings application. After
inlining, verify `settings_manager.py` stays under 250 lines.

---

## What is NOT in scope

- `loading_utils.py` — still has 3 active functions
  (`get_loading_status`, `force_reload_channel_history`,
  `get_history_statistics`). Keep as-is.
- `settings_manager.py` — actively called during history loading.
- All Discord operation files (`discord_fetcher.py`,
  `discord_converter.py`, `discord_loader.py`,
  `realtime_settings_parser.py`) — all actively called.
- `storage.py`, `prompts.py`, `message_processing.py` — core data
  modules, all actively used.
- `cleanup_coordinator.py` — actively called from
  `channel_coordinator.py`.

---

## Verification

Before deleting, confirm zero external callers:

```bash
# management_utilities.py functions (expect only settings_manager for validate_setting_value)
grep -rn "clear_channel_settings\|get_settings_statistics\|validate_setting_value\|get_channel_setting_summary\|bulk_clear_settings" --include="*.py" | grep -v __pycache__ | grep -v "docs/" | grep -v management_utilities | grep -v api_imports | grep -v api_exports

# api_imports.py (should only be referenced by __init__.py)
grep -rn "api_imports" --include="*.py" | grep -v __pycache__ | grep -v "docs/" | grep -v "api_imports.py"

# api_exports.py (should only be referenced by __init__.py)
grep -rn "api_exports" --include="*.py" | grep -v __pycache__ | grep -v "docs/" | grep -v "api_exports.py"

# loading.py callers (should only be api_imports.py and __init__.py)
grep -rn "from.*loading import\|from.*history.*import.*load_channel_history" --include="*.py" | grep -v __pycache__ | grep -v "docs/"

# Confirm validate_setting_value is inlined before deleting management_utilities
grep -rn "validate_setting_value" --include="*.py" | grep -v __pycache__ | grep -v "docs/"
```

---

## Files Changed Summary

| File | Action |
|------|--------|
| `utils/history/api_imports.py` | DELETE |
| `utils/history/api_exports.py` | DELETE |
| `utils/history/management_utilities.py` | DELETE (after inlining validate_setting_value) |
| `utils/history/loading.py` | DELETE (after moving load_channel_history) |
| `utils/history/__init__.py` | MODIFY — inline imports, define __all__ |
| `utils/history/channel_coordinator.py` | MODIFY — add load_channel_history() |
| `utils/history/settings_manager.py` | MODIFY — inline validate_setting_value() |
| `STATUS.md` | UPDATE |
| `HANDOFF.md` | UPDATE |
| `README.md` | UPDATE (if history/ file list shown) |

---

## Testing

1. **Bot starts cleanly**: no import errors in logs
2. **History loads on first message**: channel_history populated
3. **Settings restored**: system prompt, AI provider persist across restart
4. **Bot responds**: direct mention → context built → response sent
5. **Commands work**: `!status`, `!prompt`, `!ai`, `!history`, `!summary`
6. **No stale imports**: `grep -rn "api_imports\|api_exports\|management_utilities\|from.*\.loading import" --include="*.py" | grep -v __pycache__ | grep -v docs/` returns nothing

---

## Risk Assessment

**Low.** Three of the four deleted files are pure indirection with a
single caller (`__init__.py`). The fourth (`management_utilities.py`)
has one active function (`validate_setting_value`) which is inlined
into `settings_manager.py` before deletion — the remaining 4
functions are confirmed dead. The `loading.py` function is a 3-line
wrapper that moves into `channel_coordinator.py` with identical
behavior. All external imports (`from utils.history import X`)
continue to work because `__init__.py` still re-exports the same
names from the same source modules — just without the intermediate
passthrough files.

---

## Constraints

1. Full files only for modified files
2. Increment version numbers
3. 250-line limit — verify `__init__.py` fits after inlining
4. All development on `claude-code` branch
5. Run grep verification BEFORE deleting
6. `from utils.history import X` must continue to work for all
   currently-used names
