"""
History management package for Discord bot.
Provides backward compatibility by exposing all the functions and variables
that were previously in history_utils.py.
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
    load_channel_history
)

# Make all the main functions and variables available at package level
# This ensures existing imports like `from utils.history_utils import channel_history` 
# still work with `from utils.history import channel_history`

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
    
    # Loading
    'load_channel_history'
]
