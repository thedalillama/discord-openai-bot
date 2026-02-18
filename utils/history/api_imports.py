# utils/history/api_imports.py
# Version 1.3.0
"""
API imports coordination for history package.

CHANGES v1.3.0: Dead code cleanup (SOW v2.16.0)
- REMOVED: fetch_recent_messages_new import (dead code)
- REMOVED: fetch_recent_messages re-export via fetch_recent_messages_compat (dead code)
- REMOVED: settings_coordinator imports (file deleted)

CHANGES v1.2.0: Removed obsolete coordination imports
CHANGES v1.1.0: Removed obsolete settings_parser imports
"""

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

from .prompts import (
    get_system_prompt,
    set_system_prompt,
    get_ai_provider,
    set_ai_provider,
    remove_ai_provider,
    remove_system_prompt
)

from .loading import (
    load_channel_history,
    get_loading_status,
    force_reload_channel_history,
    get_history_statistics
)

from .discord_fetcher import (
    fetch_messages_from_discord as fetch_messages_from_discord_new,
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

from .discord_loader import (
    load_messages_from_discord,
    process_discord_messages,
    extract_prompt_from_update_message,
    count_processable_messages,
)

from .settings_manager import (
    apply_restored_settings,
    validate_parsed_settings,
    get_restoration_summary,
    apply_individual_setting
)

from .management_utilities import (
    clear_channel_settings,
    get_settings_statistics,
    validate_setting_value,
    get_channel_setting_summary,
    bulk_clear_settings
)
