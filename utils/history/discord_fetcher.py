# utils/history/discord_fetcher.py
# Version 1.2.0
"""
Discord API interaction functionality for fetching messages.

CHANGES v1.2.0: Dead code cleanup (SOW v2.16.0)
- REMOVED: fetch_recent_messages() function (dead code, no active callers)
- REMOVED: INITIAL_HISTORY_LOAD import (no longer needed)

CHANGES v1.1.0: Fetch all messages for complete settings restoration
- FIXED: Removed INITIAL_HISTORY_LOAD limit from fetch_messages_from_discord()

This module handles the low-level Discord API interactions for fetching messages
from Discord channels. It focuses purely on API calls and basic error handling,
with no message processing or settings parsing.
"""
from utils.logging_utils import get_logger

logger = get_logger('history.discord_fetcher')

async def fetch_messages_from_discord(channel, is_automatic):
    """
    Fetch all messages from Discord API without any processing.

    Fetches the complete channel history so that real-time settings parsing
    can find the most recent confirmed settings regardless of how far back
    they appear. The downstream pipeline (settings parser, converter, trimmer)
    already handles large message sets correctly.

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

    logger.info(f"Fetching all messages from Discord API for channel #{channel_name} ({channel_id})")
    logger.debug(f"Automatic loading: {is_automatic}, fetching full channel history (no limit)")

    messages = []
    should_skip_first = is_automatic
    message_count = 0
    skipped_count = 0

    async for message in channel.history(limit=None):
        message_count += 1

        logger.debug(f"Fetched Discord message {message_count}: {message.content[:80]}...")

        if should_skip_first:
            should_skip_first = False
            skipped_count += 1
            logger.debug(f"Skipping newest message to avoid duplicate during automatic loading")
            continue

        messages.insert(0, message)

    logger.info(f"Discord API fetch complete: {message_count} total messages, {skipped_count} skipped, {len(messages)} kept")

    return messages, skipped_count
