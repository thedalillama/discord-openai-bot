# utils/history/api_imports.py
# Version 1.2.0
"""
API imports coordination for history package.

CHANGES v1.2.0: Removed obsolete coordination imports
- Removed settings_parser.py imports (deleted in refactoring)
- Added settings_coordinator.py imports for simplified architecture
- Updated to support single-method settings persistence

CHANGES v1.1.0: Removed obsolete settings_parser imports
- Removed settings_parser.py imports (deleted in refactoring)
- Maintained all other imports for backward compatibility
- Updated to support simplified architecture with realtime parsing only

This module groups related imports for better organization and maintainability.
Created during refactoring to reduce utils/history/__init__.py from 263 to under 250 lines
while maintaining 100% backward compatibility.

All imports here are re-exported through __init__.py to maintain the existing public API.
"""

# Storage imports - Core data structures and basic operations
from .storage import (
    channel_history,
    loaded_history_channels,
    channel_locks,
    channel_system_prompts,
    channel_ai_providers,
    get_or_create_channel_lock,
    is_channel_history_loaded,
    mark_channel_history_loaded,
    get_channel_history,
    add_message_to_history,
    trim_channel_history,
    clear_channel_history,
    filter_channel_history
)

# Message processing imports - Filtering, formatting, API preparation
from .message_processing import (
    is_bot_command,
    is_history_output,
    should_skip_message_from_history,
    create_user_message,
    create_assistant_message,
    create_system_update_message,
    prepare_messages_for_api,
    extract_system_prompt_updates
)

# Prompt and AI provider management imports
from .prompts import (
    get_system_prompt,
    set_system_prompt,
    get_ai_provider,
    set_ai_provider,
    remove_ai_provider,
    remove_system_prompt
)

# History loading functionality imports
from .loading import (
    load_channel_history,
    get_loading_status,
    force_reload_channel_history,
    get_history_statistics
)

# Discord module imports - Refactored modules (v2.2.0)
from .discord_fetcher import (
    fetch_messages_from_discord as fetch_messages_from_discord_new,
    fetch_recent_messages as fetch_recent_messages_new
)

from .discord_converter import (
    convert_discord_messages as convert_discord_messages_new,
    count_convertible_messages as count_convertible_messages_new,
    filter_messages_for_conversion,
    validate_discord_message,
    extract_message_metadata
)

from .realtime_settings_parser import (
    parse_settings_during_load,
    extract_prompt_from_update_message as extract_prompt_from_update_message_new
)

# Discord loader coordination imports - Main coordination functions
from .discord_loader import (
    load_messages_from_discord,
    process_discord_messages,
    extract_prompt_from_update_message,
    count_processable_messages,
    fetch_recent_messages_compat as fetch_recent_messages
)

# Settings management imports (backup functions removed in v1.1.0)
from .settings_manager import (
    apply_restored_settings,
    validate_parsed_settings,
    get_restoration_summary,
    apply_individual_setting
)

# Management utilities imports (extracted in v1.1.0)
from .management_utilities import (
    clear_channel_settings,
    get_settings_statistics,
    validate_setting_value,
    get_channel_setting_summary,
    bulk_clear_settings
)
