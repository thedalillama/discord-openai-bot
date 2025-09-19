# utils/history/discord_fetcher.py
# Version 1.0.0
"""
Discord API interaction functionality for fetching messages.

This module handles the low-level Discord API interactions for fetching messages
from Discord channels. It focuses purely on API calls and basic error handling,
with no message processing or settings parsing.

Extracted from discord_loader.py in refactoring to maintain 200-line limit.
Part of the real-time settings parsing architecture preparation.
"""
from config import INITIAL_HISTORY_LOAD
from utils.logging_utils import get_logger

logger = get_logger('history.discord_fetcher')

async def fetch_messages_from_discord(channel, is_automatic):
    """
    Fetch messages from Discord API without any processing.
    
    This function handles the core Discord API interaction, fetching raw messages
    and performing basic filtering, but does no conversion or processing.
    
    Args:
        channel: Discord channel object to fetch messages from
        is_automatic: Whether this is automatic loading (skips newest message to avoid duplicates)
        
    Returns:
        tuple: (raw_discord_messages, skipped_count)
        
    Raises:
        Exception: If Discord API calls fail
    """
    channel_id = channel.id
    channel_name = channel.name
    
    logger.info(f"Fetching messages from Discord API for channel #{channel_name} ({channel_id})")
    logger.debug(f"Automatic loading: {is_automatic}, will fetch up to {INITIAL_HISTORY_LOAD} messages")
    
    messages = []
    
    # Flag to skip the first message if automatic loading
    should_skip_first = is_automatic
    
    message_count = 0
    skipped_count = 0
    
    logger.debug(f"Fetching up to {INITIAL_HISTORY_LOAD} messages from Discord API")
    
    # Fetch messages from Discord API
    async for message in channel.history(limit=INITIAL_HISTORY_LOAD):
        message_count += 1
        
        logger.debug(f"Fetched Discord message {message_count}: {message.content[:80]}...")
        
        # Skip the first message if automatic loading to avoid duplicates
        if should_skip_first:
            should_skip_first = False
            skipped_count += 1
            logger.debug(f"Skipping newest message to avoid duplicate during automatic loading")
            continue
        
        # Add to our list (in reverse, since Discord returns newest first)
        messages.insert(0, message)
    
    logger.info(f"Discord API fetch complete: {message_count} total messages, {skipped_count} skipped, {len(messages)} kept")
    
    return messages, skipped_count

async def fetch_recent_messages(channel, limit=None):
    """
    Fetch recent messages from a Discord channel with optional limit.
    
    This is a utility function for fetching messages without the full processing
    pipeline, useful for lighter operations or testing.
    
    Args:
        channel: Discord channel object
        limit: Maximum number of messages to fetch (default: INITIAL_HISTORY_LOAD)
        
    Returns:
        list: List of Discord message objects (newest first)
        
    Raises:
        Exception: If Discord API call fails
    """
    if limit is None:
        limit = INITIAL_HISTORY_LOAD
    
    logger.debug(f"Fetching {limit} recent messages from #{channel.name}")
    
    messages = []
    try:
        async for message in channel.history(limit=limit):
            messages.append(message)
        
        logger.debug(f"Successfully fetched {len(messages)} messages")
        return messages
        
    except Exception as e:
        logger.error(f"Failed to fetch messages from #{channel.name}: {e}")
        raise
