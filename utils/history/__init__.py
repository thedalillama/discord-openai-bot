# utils/history/__init__.py
# Version 3.2.0
"""
History management package for Discord bot.

CHANGES v3.2.0: Consolidation — remove passthrough layers (SOW v5.11.0)
- DELETED: api_imports.py, api_exports.py (pure passthrough files)
- DELETED: loading.py (passthrough; load_channel_history moved to channel_coordinator.py)
- MODIFIED: __init__.py now imports directly from source modules
- MODIFIED: __all__ trimmed to only the 11 symbols external code actually imports
- NOTE: Internal modules continue to import directly from submodules
  (e.g. `from utils.history.message_processing import prepare_messages_for_api`)
  and are unaffected by this change.

CHANGES v3.1.0: Dead code cleanup (SOW v5.10.1)
- REMOVED: diagnostics.py imports

CHANGES v3.0.0: Major architecture simplification
- REMOVED: settings_parser.py, settings_backup.py

Public API — only the symbols external code actually imports from this package.
All other history internals are accessed directly from their submodules.
"""

from .storage import (
    channel_history,
    loaded_history_channels,
    channel_system_prompts,
    channel_ai_providers,
)

from .prompts import (
    get_system_prompt,
    set_system_prompt,
    remove_system_prompt,
    get_ai_provider,
    set_ai_provider,
    remove_ai_provider,
)

from .channel_coordinator import load_channel_history

__all__ = [
    # Storage
    'channel_history',
    'loaded_history_channels',
    'channel_system_prompts',
    'channel_ai_providers',
    # Prompts & providers
    'get_system_prompt',
    'set_system_prompt',
    'remove_system_prompt',
    'get_ai_provider',
    'set_ai_provider',
    'remove_ai_provider',
    # Loading
    'load_channel_history',
]
