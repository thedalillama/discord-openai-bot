# utils/history/discord_converter.py
# Version 1.0.1
"""
Discord message conversion functionality for standardizing message format.

CHANGES v1.0.1: Filter noise bot messages at load time (SOW v2.19.0)
- ADDED: is_history_output import
- MODIFIED: convert_discord_messages() now checks is_history_output() before
  storing bot messages in channel_history
- RESULT: Command confirmations and noise messages are excluded from channel_history
  at load time; settings persistence messages pass through unaffected since they
  are not matched by is_history_output()

This module handles the conversion of Discord message objects into the standardized
message format used by AI providers. It focuses on message transformation,
filtering, and formatting logic for Discord-specific content.

Extracted from discord_loader.py in refactoring to maintain 200-line limit.
Part of the real-time settings parsing architecture preparation.
"""
from utils.logging_utils import get_logger
from .storage import add_message_to_history
from .message_processing import (
    should_skip_message_from_history, create_user_message,
    create_assistant_message, is_history_output
)

logger = get_logger('history.discord_converter')


async def convert_discord_messages(channel, messages):
    """
    Convert a list of Discord message objects into standardized conversation history format.

    Bot messages are filtered through is_history_output() before storage —
    command confirmations and noise are excluded while settings persistence
    messages pass through unaffected.

    Args:
        channel: Discord channel object (for bot identity checking)
        messages: List of Discord message objects to convert

    Returns:
        int: Number of messages successfully converted and added to history
    """
    channel_id = channel.id
    channel_name = channel.name
    converted_count = 0
    noise_skipped = 0

    logger.debug(f"Converting {len(messages)} Discord messages for channel #{channel_name}")

    for i, message in enumerate(messages):
        try:
            # Skip setprompt commands since they're handled by settings parser
            if message.content.startswith('!setprompt'):
                logger.debug(f"Skipping setprompt command (handled by settings parser)")
                continue

            if message.author == channel.guild.me:
                # Bot message — filter noise before storing.
                # Settings persistence messages ("Auto-response is now", etc.) are
                # NOT matched by is_history_output() and will pass through correctly.
                if is_history_output(message.content):
                    noise_skipped += 1
                    logger.debug(f"Skipping noise bot message: {message.content[:60]}...")
                    continue
                bot_message = create_assistant_message(message.content)
                add_message_to_history(channel_id, bot_message)
                converted_count += 1

            else:
                # User message — convert to user format with proper naming
                user_message = create_user_message(
                    message.author.display_name,
                    message.content,
                    len(messages)
                )
                add_message_to_history(channel_id, user_message)
                converted_count += 1

            if (i + 1) % 10 == 0:
                logger.debug(f"Converted {i + 1}/{len(messages)} messages")

        except Exception as e:
            logger.error(f"Error converting message {i+1}: {e}")
            logger.debug(f"Problematic message content: {message.content[:100]}...")
            continue

    logger.debug(
        f"Message conversion complete for #{channel_name}: "
        f"{converted_count} converted, {noise_skipped} noise messages skipped"
    )

    return converted_count


def count_convertible_messages(messages, channel):
    """
    Count how many messages would be converted (not skipped) from a list.

    Args:
        messages: List of Discord message objects
        channel: Discord channel object (for bot identity checking)

    Returns:
        tuple: (convertible_count, skip_count, skip_reasons)
    """
    convertible_count = 0
    skip_count = 0
    skip_reasons = {}

    for message in messages:
        is_bot_message = message.author == channel.guild.me
        should_skip, skip_reason = should_skip_message_from_history(message, is_bot_message)

        if should_skip:
            skip_count += 1
            skip_reasons[skip_reason] = skip_reasons.get(skip_reason, 0) + 1
        else:
            convertible_count += 1

    return convertible_count, skip_count, skip_reasons


def filter_messages_for_conversion(messages, channel):
    """
    Filter Discord messages to remove those that should be skipped during conversion.

    Args:
        messages: List of Discord message objects
        channel: Discord channel object (for bot identity checking)

    Returns:
        tuple: (filtered_messages, skipped_count, skip_summary)
    """
    filtered_messages = []
    skipped_count = 0
    skip_summary = {}

    for message in messages:
        is_bot_message = message.author == channel.guild.me
        should_skip, skip_reason = should_skip_message_from_history(message, is_bot_message)

        if should_skip:
            skipped_count += 1
            skip_summary[skip_reason] = skip_summary.get(skip_reason, 0) + 1
            logger.debug(f"Filtering out message ({skip_reason}): {message.content[:30]}...")
        else:
            filtered_messages.append(message)

    logger.debug(
        f"Message filtering complete: {len(filtered_messages)} kept, {skipped_count} filtered"
    )
    if skip_summary:
        logger.debug(f"Skip reasons: {skip_summary}")

    return filtered_messages, skipped_count, skip_summary


def validate_discord_message(message):
    """
    Validate that a Discord message object has the required attributes for conversion.

    Args:
        message: Discord message object to validate

    Returns:
        tuple: (is_valid, validation_errors)
    """
    errors = []

    if not hasattr(message, 'content'):
        errors.append("Message missing 'content' attribute")
    if not hasattr(message, 'author'):
        errors.append("Message missing 'author' attribute")
    if hasattr(message, 'author') and not hasattr(message.author, 'display_name'):
        errors.append("Message author missing 'display_name' attribute")
    if not hasattr(message, 'guild'):
        errors.append("Message missing 'guild' attribute")

    is_valid = len(errors) == 0
    if not is_valid:
        logger.warning(f"Discord message validation failed: {errors}")

    return is_valid, errors


def extract_message_metadata(message):
    """
    Extract useful metadata from a Discord message for logging and analysis.

    Args:
        message: Discord message object

    Returns:
        dict: Metadata about the message
    """
    try:
        return {
            'author_name': getattr(message.author, 'display_name', 'Unknown'),
            'author_is_bot': getattr(message.author, 'bot', False),
            'content_length': len(message.content) if hasattr(message, 'content') else 0,
            'has_attachments': len(message.attachments) > 0 if hasattr(message, 'attachments') else False,
            'channel_name': getattr(message.channel, 'name', 'Unknown') if hasattr(message, 'channel') else 'Unknown',
            'created_at': str(message.created_at) if hasattr(message, 'created_at') else 'Unknown'
        }
    except Exception as e:
        logger.error(f"Error extracting message metadata: {e}")
        return {'error': str(e)}
