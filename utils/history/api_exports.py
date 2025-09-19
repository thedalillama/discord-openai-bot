# utils/history/api_exports.py
# Version 1.0.0
"""
Public API exports for history package.

This module defines what functions and variables are available when importing 
from utils.history. Created during refactoring to reduce utils/history/__init__.py 
from 263 to under 250 lines while maintaining 100% backward compatibility.

The exports are organized by functional category for better maintainability.
"""

# Complete public API definition
__all__ = [
    # Storage (core data structures and basic operations)
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
    
    # Message processing (filtering, formatting, API preparation)
    'is_bot_command',
    'is_history_output',
    'should_skip_message_from_history',
    'create_user_message', 
    'create_assistant_message',
    'create_system_update_message',
    'prepare_messages_for_api',
    'extract_system_prompt_updates',
    
    # Prompts and providers (configuration management)
    'get_system_prompt',
    'set_system_prompt',
    'get_ai_provider', 
    'set_ai_provider',
    'remove_ai_provider',
    'remove_system_prompt',
    
    # History loading (main loading interface)
    'load_channel_history',
    'get_loading_status',
    'force_reload_channel_history', 
    'get_history_statistics',
    
    # Discord operations (message fetching and processing)
    'load_messages_from_discord',
    'process_discord_messages',
    'extract_prompt_from_update_message',
    'count_processable_messages',
    'fetch_recent_messages',
    
    # Enhanced Discord operations (new refactored functions)
    'fetch_messages_from_discord_new',
    'fetch_recent_messages_new',
    'convert_discord_messages_new',
    'count_convertible_messages_new',
    'filter_messages_for_conversion',
    'validate_discord_message',
    'extract_message_metadata',
    'parse_settings_during_load',
    'extract_prompt_from_update_message_new',
    
    # Settings parsing (configuration extraction from history)
    'parse_settings_from_history',
    'parse_system_prompt_update',
    'parse_ai_provider_change',
    'parse_auto_respond_change',
    'parse_thinking_setting_change',
    'extract_settings_by_type',
    'get_parsing_statistics',
    
    # Settings management (validation, backup, restoration)
    'apply_restored_settings',
    'validate_parsed_settings',
    'get_restoration_summary',
    'create_settings_backup',
    'restore_from_backup',
    'get_current_settings',
    'clear_channel_settings',
    'get_settings_statistics'
]

# Organized export categories for documentation and maintenance
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
    'extract_prompt_from_update_message', 'count_processable_messages', 'fetch_recent_messages'
]

SETTINGS_EXPORTS = [
    'parse_settings_from_history', 'parse_system_prompt_update', 'parse_ai_provider_change',
    'parse_auto_respond_change', 'parse_thinking_setting_change', 'extract_settings_by_type',
    'get_parsing_statistics', 'apply_restored_settings', 'validate_parsed_settings',
    'get_restoration_summary', 'create_settings_backup', 'restore_from_backup',
    'get_current_settings', 'clear_channel_settings', 'get_settings_statistics'
]
