# utils/history/__init__.py
# Version 2.5.0
"""
History management package for Discord bot.

CHANGES v2.5.0: Added settings backup module imports
- Added imports from new settings_backup.py module
- Maintained backward compatibility for backup/restore functions
- Enhanced backup capabilities while keeping settings_manager focused

CHANGES v2.4.0: Added diagnostics module imports
- Added imports from new diagnostics.py module
- Maintained backward compatibility for get_channel_diagnostics function
- Enhanced diagnostic capabilities while keeping loading_utils focused

CHANGES v2.3.0: Refactored imports for maintainability
- Split large import/export list into focused coordination modules
- Reduced from 263 to under 250 lines for better maintainability
- Maintained 100% backward compatibility with existing imports
- Organized imports and exports in dedicated modules

This package provides comprehensive conversation history management including:
- Message storage and retrieval (storage.py)
- Message processing and filtering (message_processing.py) 
- System prompt and AI provider management (prompts.py)
- Discord API interaction (discord_fetcher.py)
- Message conversion (discord_converter.py)
- Real-time settings parsing (realtime_settings_parser.py)
- Discord coordination (discord_loader.py)
- Configuration settings parsing (settings_parser.py)
- Configuration settings management (settings_manager.py)
- Settings backup and restore (settings_backup.py)
- History loading coordination (loading.py)
- Diagnostic and analysis tools (diagnostics.py)

The refactoring improves maintainability while preserving the existing API,
so existing imports like `from utils.history import channel_history` continue to work.
"""

# Import all functions and variables from coordination modules
from .api_imports import *
from .api_exports import __all__

# Import diagnostic functions from diagnostics module
from .diagnostics import (
    get_channel_diagnostics,
    identify_potential_issues,
    estimate_memory_usage,
    analyze_channel_health
)

# Import backup functions from settings_backup module
from .settings_backup import (
    create_settings_backup,
    restore_from_backup,
    get_current_settings,
    validate_backup_data,
    export_backup_to_json,
    import_backup_from_json
)

# Update __all__ to include diagnostic and backup functions
__all__ += [
    'get_channel_diagnostics',
    'identify_potential_issues', 
    'estimate_memory_usage',
    'analyze_channel_health',
    'create_settings_backup',
    'restore_from_backup',
    'get_current_settings',
    'validate_backup_data',
    'export_backup_to_json',
    'import_backup_from_json'
]

# Re-export everything to maintain the exact same public API
# This ensures existing imports like `from utils.history import channel_history` 
# still work with the new modular structure

"""
BACKWARD COMPATIBILITY: Existing code imports continue to work:
- from utils.history import load_messages_from_discord  # Still works
- from utils.history import process_discord_messages     # Still works  
- from utils.history import extract_prompt_from_update_message  # Still works
- from utils.history import get_channel_diagnostics      # Still works
- from utils.history import create_settings_backup       # Still works

NEW FUNCTIONALITY: Enhanced capabilities available via:
- from utils.history import analyze_channel_health
- from utils.history import identify_potential_issues
- from utils.history import estimate_memory_usage
- from utils.history import validate_backup_data
- from utils.history import export_backup_to_json
- from utils.history import import_backup_from_json
- All diagnostic and backup functions provide comprehensive capabilities

MAINTAINED BACKWARD COMPATIBILITY:
   - All existing imports continue to work unchanged
   - Clean API without confusing suffixes or wrappers
   - Public interface remains the same for existing code

ADDED REAL-TIME SETTINGS PARSING:
   - Settings parsed during message loading (not afterward)
   - Newest-first parsing with early termination optimization
   - Immediate application to in-memory dictionaries
   - Foundation for Configuration Persistence feature

ARCHITECTURE IMPROVEMENTS:
   - All files now under 250 lines ✅
   - Clear separation of concerns ✅
   - Better testability with focused modules ✅
   - Enhanced diagnostic capabilities ✅
   - Comprehensive backup and restore capabilities ✅
   - Ready for future Configuration Persistence implementation ✅

Future developers should:
- Use diagnostic functions for troubleshooting and analysis
- Use backup functions for disaster recovery and testing
- Leverage parse_settings_during_load for Configuration Persistence implementation
- Maintain the modular structure when adding new functionality
- Update __all__ when adding new public functions
- Keep the clean API design without unnecessary aliases or wrappers
"""
