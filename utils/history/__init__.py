# utils/history/__init__.py
# Version 2.2.0
"""
History management package for Discord bot.

CHANGES v2.2.0: Added support for refactored discord_loader modules
- Added exports for new discord_fetcher, discord_converter, realtime_settings_parser modules
- Maintained backward compatibility by exposing discord_loader functions through clean API
- Prepared for real-time Configuration Persistence features
- All refactored modules under 200 lines

CHANGES v2.1.1: Fixed imports in loading.py and removed references to deleted settings_restoration module
CHANGES v2.1.0: Updated for settings module split to maintain 200-line limit
CHANGES v2.0.0: Updated for history module refactoring

This package provides comprehensive conversation history management including:
- Message storage and retrieval (storage.py)
- Message processing and filtering (message_processing.py) 
- System prompt and AI provider management (prompts.py)
- Discord API interaction (discord_fetcher.py) - REFACTORED in v2.2.0
- Message conversion (discord_converter.py) - NEW in v2.2.0
- Real-time settings parsing (realtime_settings_parser.py) - NEW in v2.2.0
- Discord coordination (discord_loader.py) - REFACTORED in v2.2.0
- Configuration settings parsing (settings_parser.py)
- Configuration settings management (settings_manager.py)
- History loading coordination (loading.py)

The refactoring improves maintainability while preserving the existing API,
so existing imports like `from utils.history import channel_history` continue to work.
"""

# Import storage data and functions
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

# Import message processing functions
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

# Import prompt and AI provider management
from .prompts import (
    get_system_prompt,
    set_system_prompt,
    get_ai_provider,
    set_ai_provider,
    remove_ai_provider,
    remove_system_prompt
)

# Import history loading functionality
from .loading import (
    load_channel_history,
    get_loading_status,
    force_reload_channel_history,
    get_history_statistics
)

# Import refactored Discord modules (v2.2.0)
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

# Import main Discord loader functions (CLEAN API)
from .discord_loader import (
    load_messages_from_discord,
    process_discord_messages,
    extract_prompt_from_update_message,
    count_processable_messages,
    fetch_recent_messages_compat as fetch_recent_messages
)

# Import settings parsing functions
from .settings_parser import (
    parse_settings_from_history,
    parse_system_prompt_update,
    parse_ai_provider_change,
    parse_auto_respond_change,
    parse_thinking_setting_change,
    extract_settings_by_type,
    get_parsing_statistics
)

# Import settings management functions
from .settings_manager import (
    apply_restored_settings,
    validate_parsed_settings,
    get_restoration_summary,
    create_settings_backup,
    restore_from_backup,
    get_current_settings,
    clear_channel_settings,
    get_settings_statistics
)

# Make all the main functions and variables available at package level
# This ensures existing imports like `from utils.history import channel_history` 
# still work with the new modular structure

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
    
    # Loading coordination (main public interface)
    'load_channel_history',
    'get_loading_status',
    'force_reload_channel_history', 
    'get_history_statistics',
    
    # Discord API interaction (BACKWARD COMPATIBLE - existing API maintained)
    'load_messages_from_discord',
    'process_discord_messages',
    'extract_prompt_from_update_message',
    'fetch_recent_messages',
    'count_processable_messages',
    
    # NEW refactored modules (v2.2.0) - available for future use
    'fetch_messages_from_discord_new',
    'fetch_recent_messages_new',
    'convert_discord_messages_new', 
    'count_convertible_messages_new',
    'filter_messages_for_conversion',
    'validate_discord_message',
    'extract_message_metadata',
    'parse_settings_during_load',
    'extract_prompt_from_update_message_new',
    
    # Settings parsing (existing functionality)
    'parse_settings_from_history',
    'parse_system_prompt_update',
    'parse_ai_provider_change',
    'parse_auto_respond_change',
    'parse_thinking_setting_change',
    'extract_settings_by_type',
    'get_parsing_statistics',
    
    # Settings management (existing functionality) 
    'apply_restored_settings',
    'validate_parsed_settings',
    'get_restoration_summary',
    'create_settings_backup',
    'restore_from_backup',
    'get_current_settings',
    'clear_channel_settings',
    'get_settings_statistics'
]

# Package metadata
__version__ = '2.2.0'
__description__ = 'Discord bot conversation history management with real-time configuration persistence'
__refactoring_date__ = '2025-09-18'

# Development notes for future maintainers
"""
REFACTORING NOTES v2.2.0:

Major refactoring to split discord_loader.py (247 lines) into focused modules under 200 lines:

1. EXTRACTED NEW MODULES:
   - discord_fetcher.py (70 lines): Pure Discord API interactions
   - discord_converter.py (90 lines): Discord message conversion to history format
   - realtime_settings_parser.py (80 lines): Real-time settings parsing during load
   - discord_loader.py (50 lines): Clean coordination layer

2. MAINTAINED BACKWARD COMPATIBILITY:
   - All existing imports continue to work unchanged
   - Clean API without confusing suffixes or wrappers
   - Public interface remains the same for existing code

3. ADDED REAL-TIME SETTINGS PARSING:
   - Settings parsed during message loading (not afterward)
   - Newest-first parsing with early termination optimization
   - Immediate application to in-memory dictionaries
   - Foundation for Configuration Persistence feature

4. ARCHITECTURE IMPROVEMENTS:
   - All files now under 200 lines ✅
   - Clear separation of concerns ✅
   - Better testability with focused modules ✅
   - Ready for future Configuration Persistence implementation ✅

Future developers should:
- Use the _new suffixed functions for new features requiring real-time parsing
- Leverage parse_settings_during_load for Configuration Persistence implementation
- Maintain the modular structure when adding new functionality
- Update __all__ when adding new public functions
- Keep the clean API design without unnecessary aliases or wrappers

BACKWARD COMPATIBILITY: Existing code imports continue to work:
- from utils.history import load_messages_from_discord  # Still works
- from utils.history import process_discord_messages     # Still works
- from utils.history import extract_prompt_from_update_message  # Still works

NEW FUNCTIONALITY: Real-time parsing available via:
- from utils.history import parse_settings_during_load
- from utils.history import convert_discord_messages_new
- from utils.history import validate_discord_message
- All _new suffixed functions provide enhanced capabilities
"""
