# utils/history/api_exports.py
# Version 1.3.0
"""
Public API exports for history package.

CHANGES v1.3.0: Dead code cleanup (SOW v2.16.0)
- REMOVED: fetch_recent_messages from __all__ and LOADING_EXPORTS
- REMOVED: fetch_recent_messages_new from __all__
- REMOVED: coordinate_settings_restoration from __all__ and SETTINGS_EXPORTS
- REMOVED: get_settings_restoration_status from __all__ and SETTINGS_EXPORTS

CHANGES v1.2.0: Updated exports for simplified architecture
CHANGES v1.1.0: Removed obsolete settings_parser exports
"""

__all__ = [
    # Storage
    'channel_history',
    'loaded_history_channels',
    'channel_locks',
    'channel_system_prompts',
    'channel_ai_providers',
    'get_or_create_channel_lock',
    'is_channel_history_loaded',
    'mark_channel_history_loaded',
    'get_channel_history',
    'add_message_to_history',
    'trim_channel_history',
    'clear_channel_history',
    'filter_channel_history',

    # Message processing
    'is_bot_command',
    'is_history_output',
    'should_skip_message_from_history',
    'create_user_message',
    'create_assistant_message',
    'create_system_update_message',
    'prepare_messages_for_api',
    'extract_system_prompt_updates',

    # Prompts and providers
    'get_system_prompt',
    'set_system_prompt',
    'get_ai_provider',
    'set_ai_provider',
    'remove_ai_provider',
    'remove_system_prompt',

    # History loading
    'load_channel_history',
    'get_loading_status',
    'force_reload_channel_history',
    'get_history_statistics',

    # Discord operations
    'load_messages_from_discord',
    'process_discord_messages',
    'extract_prompt_from_update_message',
    'count_processable_messages',

    # Enhanced Discord operations
    'fetch_messages_from_discord_new',
    'convert_discord_messages_new',
    'count_convertible_messages_new',
    'filter_messages_for_conversion',
    'validate_discord_message',
    'extract_message_metadata',
    'parse_settings_during_load',
    'extract_prompt_from_update_message_new',

    # Settings management
    'apply_restored_settings',
    'validate_parsed_settings',
    'get_restoration_summary',
    'apply_individual_setting',
    'clear_channel_settings',
    'get_settings_statistics',
    'validate_setting_value',
    'get_channel_setting_summary',
    'bulk_clear_settings'
]

STORAGE_EXPORTS = [
    'channel_history', 'loaded_history_channels', 'channel_locks',
    'channel_system_prompts', 'channel_ai_providers', 'get_or_create_channel_lock',
    'is_channel_history_loaded', 'mark_channel_history_loaded', 'get_channel_history',
    'add_message_to_history', 'trim_channel_history', 'clear_channel_history',
    'filter_channel_history'
]

PROCESSING_EXPORTS = [
    'is_bot_command', 'is_history_output', 'should_skip_message_from_history',
    'create_user_message', 'create_assistant_message', 'create_system_update_message',
    'prepare_messages_for_api', 'extract_system_prompt_updates'
]

LOADING_EXPORTS = [
    'load_channel_history', 'get_loading_status', 'force_reload_channel_history',
    'get_history_statistics', 'load_messages_from_discord', 'process_discord_messages',
    'extract_prompt_from_update_message', 'count_processable_messages'
]

SETTINGS_EXPORTS = [
    'apply_restored_settings', 'validate_parsed_settings', 'get_restoration_summary',
    'apply_individual_setting', 'clear_channel_settings', 'get_settings_statistics',
    'validate_setting_value', 'get_channel_setting_summary', 'bulk_clear_settings'
]
