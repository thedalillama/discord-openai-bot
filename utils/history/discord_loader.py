# utils/history/discord_loader.py
# Version 2.4.0
"""
Discord API interaction coordination for message history loading.

CHANGES v2.4.0: Pass msg.id to create_*_message() in _seed_history_from_db()
  so seeded history entries carry _msg_id for Layer 2 deduplication

CHANGES v2.3.0: Seed in-memory history from SQLite before delta fetch so the
  bot has conversation context on the first message after restart
CHANGES v2.2.0: Startup fetch optimization — restore settings from SQLite, then
  fetch only delta messages (after last_processed_id) instead of full history
CHANGES v2.1.0: Dead code cleanup (SOW v2.16.0)
- REMOVED: fetch_recent_messages_compat() function (dead code, no active callers)
- REMOVED: fetch_recent_messages import from discord_fetcher

CHANGES v2.0.0: Refactored into focused modules:
- discord_fetcher.py: Pure Discord API interactions
- discord_converter.py: Message conversion to history format
- realtime_settings_parser.py: Real-time settings detection and application
- This file: Coordination and public interface
"""
import asyncio
from utils.logging_utils import get_logger
from utils.message_store import get_last_processed_id, get_channel_messages
from config import MAX_HISTORY
from .discord_fetcher import fetch_messages_from_discord
from .discord_converter import convert_discord_messages, count_convertible_messages
from .realtime_settings_parser import parse_settings_during_load, restore_settings_from_db
from .storage import add_message_to_history
from .message_processing import (
    create_user_message, create_assistant_message,
    is_history_output, is_settings_persistence_message,
)

logger = get_logger('history.discord_loader')


def _seed_history_from_db(channel_id):
    """Populate in-memory channel_history from SQLite for a channel.

    Loads recent non-deleted messages, applies the same noise filters as
    convert_discord_messages (skip ℹ️ output, commands, etc.), and adds
    the last MAX_HISTORY surviving messages to the in-memory buffer.

    Fetches MAX_HISTORY*10 rows from DB so that heavy-noise channels
    (lots of ℹ️ bot output) still yield a full MAX_HISTORY usable messages.

    Returns count of messages added.
    """
    messages = get_channel_messages(channel_id)
    # Pull a wide window to survive heavy bot-output channels, then trim after filter
    window = messages[-(MAX_HISTORY * 10):] if len(messages) > MAX_HISTORY * 10 else messages
    kept = []
    for msg in window:
        content = msg.content or ""
        if not content:
            continue
        if content.startswith('!'):
            continue
        if msg.is_bot_author:
            if is_history_output(content) or is_settings_persistence_message(content):
                continue
            kept.append(create_assistant_message(content, msg_id=msg.id))
        else:
            kept.append(create_user_message(msg.author_name, content, msg_id=msg.id))
    # Take only the last MAX_HISTORY after filtering
    for entry in kept[-MAX_HISTORY:]:
        add_message_to_history(channel_id, entry)
    return len(kept[-MAX_HISTORY:])


async def load_messages_from_discord(channel, is_automatic):
    """
    Load messages from Discord API and process them with real-time settings parsing.

    Orchestrates:
    1. Restore settings from SQLite (avoids full Discord history fetch)
    2. Seed in-memory history from SQLite (recent MAX_HISTORY messages)
    3. Fetch only new messages since last DB-recorded ID (delta fetch)
    4. Parse settings from any fresh delta messages
    5. Convert delta messages into in-memory history format

    Args:
        channel: Discord channel object to load messages from
        is_automatic: Whether this is automatic loading (skips newest message to
            avoid duplicates; ignored when last_id is set)

    Returns:
        tuple: (processed_messages_count, skipped_messages_count)

    Raises:
        Exception: If Discord API calls fail or message processing encounters errors
    """
    channel_id = channel.id
    channel_name = channel.name

    logger.info(
        f"Starting coordinated message loading for channel #{channel_name} ({channel_id})")

    try:
        # Step 1: Restore settings from SQLite (no Discord fetch needed)
        settings_result = await restore_settings_from_db(channel_id)
        logger.debug(
            f"DB settings restore: {settings_result['total_found']} settings applied")

        # Step 2: Seed in-memory history from SQLite
        seeded = await asyncio.to_thread(_seed_history_from_db, channel_id)
        logger.debug(f"Seeded {seeded} messages into in-memory history from DB")

        # Step 3: Delta fetch — only messages newer than last DB record
        last_id = await asyncio.to_thread(get_last_processed_id, channel_id)
        messages, skipped_count = await fetch_messages_from_discord(
            channel, is_automatic, after_id=last_id)
        logger.debug(f"Fetched {len(messages)} delta messages from Discord API")

        # Step 4: Parse any settings in the fresh delta (e.g. settings changed
        # between backfill and this history load)
        if messages:
            await parse_settings_during_load(messages, channel_id)

        # Step 5: Add delta messages to in-memory history
        converted_count = await convert_discord_messages(channel, messages)
        logger.info(
            f"Coordinated loading complete for #{channel_name}: "
            f"{seeded} seeded from DB, {converted_count} delta converted, "
            f"{skipped_count} skipped")
        return seeded + converted_count, skipped_count

    except Exception as e:
        logger.error(
            f"Error in coordinated message loading for #{channel_name}: {e}")
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
