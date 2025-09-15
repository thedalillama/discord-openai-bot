# utils/history/__init__.py
# Version 2.1.1
"""
History management package for Discord bot.

CHANGES v2.1.1: Fixed imports in loading.py and removed references to deleted settings_restoration module
CHANGES v2.1.0: Updated for settings module split to maintain 200-line limit
- Split settings_restoration.py into settings_parser.py and settings_manager.py
- Updated exports to reflect new modular structure
- All modules now under 200 lines

CHANGES v2.0.0: Updated for history module refactoring
- Added exports for new discord_loader and settings_restoration modules
- Maintained backward compatibility by exposing all the functions and variables
  that were previously in history_utils.py and the monolithic loading.py
- Updated documentation to reflect new modular structure

This package provides comprehensive conversation history management including:
- Message storage and retrieval (storage.py)
- Message processing and filtering (message_processing.py) 
- System prompt and AI provider management (prompts.py)
- Discord API interaction (discord_loader.py) - NEW in v2.0.0
- Configuration settings parsing (settings_parser.py) - NEW in v2.1.0
- Configuration settings management (settings_manager.py) - NEW in v2.1.0
- History loading coordination (loading.py) - REFACTORED in v2.0.0

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

# Import Discord API interaction functions (NEW in v2.0.0)
from .discord_loader import (
    load_messages_from_discord,
    process_discord_messages,
    extract_prompt_from_update_message,
    fetch_recent_messages,
    count_processable_messages
)

# Import settings parsing functions (NEW in v2.1.0)
from .settings_parser import (
    parse_settings_from_history,
    parse_system_prompt_update,
    parse_ai_provider_change,
    parse_auto_respond_change,
    parse_thinking_setting_change,
    extract_settings_by_type,
    get_parsing_statistics
)

# Import settings management functions (NEW in v2.1.0)
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
    
    # Discord API interaction (NEW in v2.0.0)
    'load_messages_from_discord',
    'process_discord_messages',
    'extract_prompt_from_update_message',
    'fetch_recent_messages',
    'count_processable_messages',
    
    # Settings parsing (NEW in v2.1.0)
    'parse_settings_from_history',
    'parse_system_prompt_update',
    'parse_ai_provider_change',
    'parse_auto_respond_change',
    'parse_thinking_setting_change',
    'extract_settings_by_type',
    'get_parsing_statistics',
    
    # Settings management (NEW in v2.1.0) 
    'apply_restored_settings',
    'validate_parsed_settings',
    'get_restoration_summary',
    'create_settings_backup',
    'restore_from_backup',
    'get_current_settings',
    'clear_channel_settings',
    'get_settings_statistics'
]

# Backward compatibility aliases for any renamed functions
# (None needed for this refactoring, but this is where they would go)

# Package metadata
__version__ = '2.1.1'
__description__ = 'Discord bot conversation history management with configuration persistence'
__refactoring_date__ = '2025-09-15'

# Development notes for future maintainers
"""
REFACTORING NOTES v2.1.1:

Fixed critical import errors after settings module split:
- Removed all references to deleted settings_restoration.py
- Updated imports to use settings_parser.py and settings_manager.py
- Ensured proper version tracking and documentation

REFACTORING NOTES v2.1.0:

Split settings_restoration.py into two focused modules to maintain 200-line limit:
- settings_parser.py: Pure parsing functions with no side effects
- settings_manager.py: Validation, application, and management functions

REFACTORING NOTES v2.0.0:

The history package was refactored to improve maintainability and prepare for
the Configuration Persistence feature. The changes include:

1. SPLIT LARGE FILES:
   - utils/history/loading.py (280 lines) → 3 focused modules
   - discord_loader.py: Discord API interactions 
   - settings modules: Configuration persistence foundation
   - loading.py: Coordination and public interface

2. MAINTAINED BACKWARD COMPATIBILITY:
   - All existing imports continue to work unchanged
   - Public API remains the same
   - Internal improvements don't affect external users

3. ADDED NEW FUNCTIONALITY:
   - Settings restoration from conversation history
   - Better validation and error handling
   - Enhanced logging and monitoring utilities

4. IMPROVED ARCHITECTURE:
   - Clear separation of concerns
   - Better testability with focused modules
   - Foundation for configuration persistence feature
   - Comprehensive documentation

Future developers should:
- Use the new settings_parser and settings_manager functions for persistence features
- Leverage discord_loader for any new Discord API interactions
- Maintain the modular structure when adding new functionality
- Update __all__ when adding new public functions
"""
