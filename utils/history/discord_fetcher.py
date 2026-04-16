# utils/history/discord_fetcher.py
# Version 1.3.0
"""
Discord API interaction functionality for fetching messages.

CHANGES v1.3.0: Delta fetch — accept after_id to fetch only messages newer than
  the last DB-recorded ID; add import discord
CHANGES v1.2.0: Dead code cleanup (SOW v2.16.0)
- REMOVED: fetch_recent_messages() function (dead code, no active callers)
- REMOVED: INITIAL_HISTORY_LOAD import (no longer needed)

CHANGES v1.1.0: Fetch all messages for complete settings restoration
- FIXED: Removed INITIAL_HISTORY_LOAD limit from fetch_messages_from_discord()

This module handles the low-level Discord API interactions for fetching messages
from Discord channels. It focuses purely on API calls and basic error handling,
with no message processing or settings parsing.
"""
import discord
from utils.logging_utils import get_logger

logger = get_logger('history.discord_fetcher')


async def fetch_messages_from_discord(channel, is_automatic, after_id=None):
    """
    Fetch messages from Discord API without any processing.

    When after_id is provided, fetches only messages newer than that ID
    (delta fetch — avoids pulling entire channel history on restart).
    Otherwise fetches the full channel history (legacy path).

    Args:
        channel: Discord channel object to fetch messages from
        is_automatic: Whether this is automatic loading (skips newest message to
            avoid duplicates; ignored when after_id is set)
        after_id: Optional snowflake ID; when set, only messages newer than this
            ID are fetched (oldest_first=True, no skip logic).

    Returns:
        tuple: (raw_discord_messages, skipped_count)

    Raises:
        Exception: If Discord API calls fail
    """
    channel_id = channel.id
    channel_name = channel.name

    if after_id is not None:
        logger.info(
            f"Delta fetch for #{channel_name} ({channel_id}) after id={after_id}")
        messages = []
        async for message in channel.history(
                limit=None, after=discord.Object(id=after_id), oldest_first=True):
            messages.append(message)
        logger.info(
            f"Delta fetch complete: {len(messages)} new messages for #{channel_name}")
        return messages, 0

    logger.info(
        f"Full history fetch for #{channel_name} ({channel_id})")
    messages = []
    should_skip_first = is_automatic
    message_count = 0
    skipped_count = 0

    async for message in channel.history(limit=None):
        message_count += 1
        if should_skip_first:
            should_skip_first = False
            skipped_count += 1
            logger.debug("Skipping newest message to avoid duplicate during automatic loading")
            continue
        messages.insert(0, message)

    logger.info(
        f"Full fetch complete: {message_count} total, "
        f"{skipped_count} skipped, {len(messages)} kept")
    return messages, skipped_count
