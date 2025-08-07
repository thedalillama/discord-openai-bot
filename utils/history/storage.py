"""
Storage management for Discord bot history data.
Handles all the data dictionaries and basic access operations.
"""
from collections import defaultdict
import asyncio
from utils.logging_utils import get_logger

logger = get_logger('history.storage')

# Dictionary to store conversation history for each channel
channel_history = defaultdict(list)

# Dictionary to track channels where history has been loaded, with timestamps
# Format: {channel_id: first_processed_timestamp}
loaded_history_channels = {}

# Dictionary to store locks for each channel
channel_locks = {}

# Dictionary to store custom system prompts for each channel
# Format: {channel_id: custom_prompt}
channel_system_prompts = {}

# Dictionary to store AI providers for each channel
# Format: {channel_id: provider_name}
channel_ai_providers = {}

def get_or_create_channel_lock(channel_id, channel_name=None):
    """
    Get or create a lock for a channel
    
    Args:
        channel_id: The Discord channel ID
        channel_name: Optional channel name for logging
        
    Returns:
        asyncio.Lock: The lock for this channel
    """
    if channel_id not in channel_locks:
        channel_locks[channel_id] = asyncio.Lock()
        if channel_name:
            logger.debug(f"Created new lock for channel #{channel_name}")
        else:
            logger.debug(f"Created new lock for channel {channel_id}")
    
    return channel_locks[channel_id]

def is_channel_history_loaded(channel_id):
    """
    Check if history has been loaded for a channel
    
    Args:
        channel_id: The Discord channel ID
        
    Returns:
        bool: True if history has been loaded
    """
    return channel_id in loaded_history_channels

def mark_channel_history_loaded(channel_id, timestamp):
    """
    Mark a channel as having its history loaded
    
    Args:
        channel_id: The Discord channel ID  
        timestamp: When the history was loaded
    """
    loaded_history_channels[channel_id] = timestamp
    logger.debug(f"Marked channel {channel_id} as history loaded")

def get_channel_history(channel_id):
    """
    Get the conversation history for a channel
    
    Args:
        channel_id: The Discord channel ID
        
    Returns:
        list: List of messages in the channel history
    """
    return channel_history[channel_id]

def add_message_to_history(channel_id, message):
    """
    Add a message to channel history
    
    Args:
        channel_id: The Discord channel ID
        message: Message dict with role, content, etc.
    """
    channel_history[channel_id].append(message)

def trim_channel_history(channel_id, max_length):
    """
    Trim channel history to maximum length
    
    Args:
        channel_id: The Discord channel ID
        max_length: Maximum number of messages to keep
        
    Returns:
        tuple: (old_length, new_length) for logging
    """
    old_length = len(channel_history[channel_id])
    if old_length > max_length:
        channel_history[channel_id] = channel_history[channel_id][-max_length:]
        new_length = len(channel_history[channel_id])
        return old_length, new_length
    return old_length, old_length

def clear_channel_history(channel_id):
    """
    Clear all history for a channel
    
    Args:
        channel_id: The Discord channel ID
        
    Returns:
        int: Number of messages that were cleared
    """
    count = len(channel_history[channel_id])
    channel_history[channel_id] = []
    return count

def filter_channel_history(channel_id, filter_func):
    """
    Filter channel history using a function
    
    Args:
        channel_id: The Discord channel ID
        filter_func: Function that takes a message and returns True to keep it
        
    Returns:
        tuple: (original_count, filtered_count, removed_count)
    """
    original_count = len(channel_history[channel_id])
    channel_history[channel_id] = [msg for msg in channel_history[channel_id] if filter_func(msg)]
    filtered_count = len(channel_history[channel_id])
    removed_count = original_count - filtered_count
    
    return original_count, filtered_count, removed_count
