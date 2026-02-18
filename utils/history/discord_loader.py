# utils/history/discord_loader.py
# Version 2.1.0
"""
Discord API interaction coordination for message history loading.

CHANGES v2.1.0: Dead code cleanup (SOW v2.16.0)
- REMOVED: fetch_recent_messages_compat() function (dead code, no active callers)
- REMOVED: fetch_recent_messages import from discord_fetcher

CHANGES v2.0.0: Refactored into focused modules:
- discord_fetcher.py: Pure Discord API interactions
- discord_converter.py: Message conversion to history format
- realtime_settings_parser.py: Real-time settings detection and application
- This file: Coordination and public interface
"""
from utils.logging_utils import get_logger
from .discord_fetcher import fetch_messages_from_discord
from .discord_converter import convert_discord_messages, count_convertible_messages
from .realtime_settings_parser import parse_settings_during_load

logger = get_logger('history.discord_loader')

async def load_messages_from_discord(channel, is_automatic):
    """
    Load messages from Discord API and process them with real-time settings parsing.

    Orchestrates:
    1. Fetching all raw messages from Discord API
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
        messages, skipped_count = await fetch_messages_from_discord(channel, is_automatic)
        logger.debug(f"Fetched {len(messages)} messages from Discord API")

        settings_result = await parse_settings_during_load(messages, channel_id)
        logger.debug(f"Real-time settings parsing found {settings_result['total_found']} settings")

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
    Maintained for backward compatibility.
    """
    return await convert_discord_messages(channel, messages)

def extract_prompt_from_update_message(message):
    """
    Extract system prompt text from a bot confirmation message.
    Maintained for backward compatibility.
    """
    from .realtime_settings_parser import extract_prompt_from_update_message as extract_func
    return extract_func(message)

def count_processable_messages(messages, channel):
    """
    Count how many messages would be processed from a list.
    Maintained for backward compatibility.
    """
    return count_convertible_messages(messages, channel)
