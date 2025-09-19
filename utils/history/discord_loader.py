# utils/history/discord_loader.py
# Version 2.0.0
"""
Discord API interaction coordination for message history loading.

This module provides the main coordination layer for Discord message loading,
orchestrating the interaction between message fetching, message conversion, and
real-time settings parsing.

REFACTORED in v2.0.0: Split large monolithic file into focused modules:
- discord_fetcher.py: Pure Discord API interactions
- discord_converter.py: Message conversion to history format  
- realtime_settings_parser.py: Real-time settings detection and application
- This file: Coordination and public interface

Maintains backward compatibility with existing imports while preparing for
real-time Configuration Persistence features.
"""
from utils.logging_utils import get_logger
from .discord_fetcher import fetch_messages_from_discord, fetch_recent_messages
from .discord_converter import convert_discord_messages, count_convertible_messages
from .realtime_settings_parser import parse_settings_during_load

logger = get_logger('history.discord_loader')

async def load_messages_from_discord(channel, is_automatic):
    """
    Load messages from Discord API and process them with real-time settings parsing.
    
    This is the main coordination function that orchestrates:
    1. Fetching raw messages from Discord API
    2. Parsing settings in real-time during loading
    3. Converting messages into standardized format
    
    Args:
        channel: Discord channel object to load messages from
        is_automatic: Whether this is automatic loading (skips newest message to avoid duplicates)
        
    Returns:
        tuple: (processed_messages_count, skipped_messages_count)
        
    Raises:
        Exception: If Discord API calls fail or message processing encounters errors
    """
    channel_id = channel.id
    channel_name = channel.name
    
    logger.info(f"Starting coordinated message loading for channel #{channel_name} ({channel_id})")
    
    try:
        # Step 1: Fetch raw messages from Discord API
        messages, skipped_count = await fetch_messages_from_discord(channel, is_automatic)
        logger.debug(f"Fetched {len(messages)} messages from Discord API")
        
        # Step 2: Parse settings in real-time during loading (newest first optimization)
        settings_result = await parse_settings_during_load(messages, channel_id)
        logger.debug(f"Real-time settings parsing found {settings_result['total_found']} settings")
        
        # Step 3: Convert messages into standardized conversation history format
        converted_count = await convert_discord_messages(channel, messages)
        logger.debug(f"Converted {converted_count} messages into history format")
        
        logger.info(f"Coordinated loading complete for #{channel_name}: {converted_count} converted, {skipped_count} skipped")
        
        return converted_count, skipped_count
        
    except Exception as e:
        logger.error(f"Error in coordinated message loading for #{channel_name}: {e}")
        raise

async def process_discord_messages(channel, messages):
    """
    Process Discord messages into standardized conversation history format.
    
    This function maintains backward compatibility with the existing API by
    delegating to the new discord_converter module.
    
    Args:
        channel: Discord channel object (for bot identity checking)
        messages: List of Discord message objects to process
        
    Returns:
        int: Number of messages successfully processed and added to history
    """
    return await convert_discord_messages(channel, messages)

def extract_prompt_from_update_message(message):
    """
    Extract system prompt text from a "System prompt updated" confirmation message.
    
    This function maintains backward compatibility with the existing API by
    delegating to the realtime_settings_parser module.
    
    Args:
        message: Discord message object containing system prompt update confirmation
        
    Returns:
        str or None: The system prompt text, or None if extraction failed
    """
    from .realtime_settings_parser import extract_prompt_from_update_message as extract_func
    return extract_func(message)

def count_processable_messages(messages, channel):
    """
    Count how many messages would be processed (not skipped) from a list.
    
    This function maintains backward compatibility with the existing API by
    delegating to the discord_converter module.
    
    Args:
        messages: List of Discord message objects
        channel: Discord channel object (for bot identity checking)
        
    Returns:
        tuple: (processable_count, skip_count, skip_reasons)
    """
    return count_convertible_messages(messages, channel)

# Re-export fetch function for backward compatibility
async def fetch_recent_messages_compat(channel, limit=None):
    """
    Fetch recent messages from a Discord channel with optional limit.
    
    This function maintains backward compatibility with the existing API.
    """
    return await fetch_recent_messages(channel, limit)
