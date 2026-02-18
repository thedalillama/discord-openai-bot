# utils/history/cleanup_coordinator.py
# Version 2.2.0
"""
Final cleanup coordination for Discord message history loading.

CHANGES v2.2.0: Trim history to MAX_HISTORY after load (SOW v2.17.0)
- ADDED: _trim_to_max_history() as Step 2 in coordinate_final_cleanup()
- RESULT: channel_history never exceeds MAX_HISTORY messages after load;
  prepare_messages_for_api() sends all stored messages with no slicing needed
- NOTE: Full history is fetched from Discord so settings parser can find
  confirmed settings anywhere in channel history. Trimming happens here,
  after settings are applied and noise is filtered, so no data is lost.

CHANGES v2.1.0: Expand filtering to include assistant-side noise (SOW v2.14.0)
- ADDED: is_history_output import for assistant message filtering
- EXPANDED: _filter_conversation_history() now filters assistant messages
  matching is_history_output()
- EXPANDED: Also filters system messages not SYSTEM_PROMPT_UPDATE records
- FIXED: Stale !setprompt reference updated to !prompt for v2.13.0 consistency

CHANGES v2.0.0: Removed legacy system prompt support
- REMOVED: Legacy system prompt restoration for old SYSTEM_PROMPT_UPDATE format
- SIMPLIFIED: Focus only on message filtering and final validation

This module coordinates final cleanup operations after message loading.
Handles message filtering, history trimming, and final validation of loaded
conversation history.

Key Responsibilities:
- Filter out unwanted messages (commands, history outputs, etc.)
- Trim history to MAX_HISTORY after settings are applied
- Perform final validation and statistics reporting
- Ensure conversation history is ready for AI usage

All system prompt handling is done via realtime parsing during Discord loading.
"""
from config import MAX_HISTORY
from utils.logging_utils import get_logger
from .storage import channel_history
from .message_processing import is_bot_command, is_history_output

logger = get_logger('history.cleanup_coordinator')


async def coordinate_final_cleanup(channel):
    """
    Coordinate final cleanup operations for a channel after history loading.

    Steps:
    1. Filter unwanted messages (commands, noise, artifacts)
    2. Trim to MAX_HISTORY most recent messages
    3. Final validation and statistics

    Args:
        channel: Discord channel object that was processed

    Returns:
        dict: Summary of cleanup operations with counts and status
    """
    channel_id = channel.id
    channel_name = channel.name

    logger.debug(f"Starting final cleanup coordination for channel #{channel_name}")

    result = {
        'messages_filtered': 0,
        'messages_trimmed': 0,
        'final_message_count': 0,
        'cleanup_status': 'started'
    }

    try:
        # Step 1: Filter unwanted messages from conversation history
        filter_result = await _filter_conversation_history(channel_id)
        result['messages_filtered'] = filter_result['removed_count']

        # Step 2: Trim to MAX_HISTORY
        # Settings are already applied and noise is filtered — safe to trim now
        trim_result = _trim_to_max_history(channel_id)
        result['messages_trimmed'] = trim_result['removed_count']

        # Step 3: Final validation and statistics
        final_result = await _perform_final_validation(channel)
        result['final_message_count'] = final_result['message_count']

        result['cleanup_status'] = 'completed'

        logger.info(f"Final cleanup completed for channel #{channel_name}: "
                    f"{result['messages_filtered']} filtered, "
                    f"{result['messages_trimmed']} trimmed to MAX_HISTORY={MAX_HISTORY}, "
                    f"{result['final_message_count']} final messages")

        return result

    except Exception as e:
        logger.error(f"Error during final cleanup for channel #{channel_name}: {e}")
        result['cleanup_status'] = f'error: {str(e)}'
        raise


async def _filter_conversation_history(channel_id):
    """
    Filter conversation history to remove unwanted messages.

    Removes bot commands, history outputs, and system artifacts not needed
    for AI context. Applies the same filtering logic as !history clean to
    ensure automatic reload and manual reload produce identical results.

    Args:
        channel_id: Discord channel ID to filter

    Returns:
        dict: Filter operation results with original/filtered/removed counts
    """
    logger.debug(f"Filtering conversation history for channel {channel_id}")

    if channel_id not in channel_history or not channel_history[channel_id]:
        logger.debug(f"No history to filter for channel {channel_id}")
        return {'original_count': 0, 'filtered_count': 0, 'removed_count': 0}

    before_count = len(channel_history[channel_id])

    channel_history[channel_id] = [
        msg for msg in channel_history[channel_id]
        if not (
            msg["role"] == "user" and
            is_bot_command(msg["content"])
        ) and not (
            msg["role"] == "assistant" and
            is_history_output(msg["content"])
        ) and not (
            msg["role"] == "system" and
            not msg["content"].startswith("SYSTEM_PROMPT_UPDATE:")
        )
    ]

    after_count = len(channel_history[channel_id])
    removed_count = before_count - after_count

    if removed_count > 0:
        logger.debug(f"Filtered {removed_count} unwanted messages from history")

    return {
        'original_count': before_count,
        'filtered_count': after_count,
        'removed_count': removed_count
    }


def _trim_to_max_history(channel_id):
    """
    Trim channel history to MAX_HISTORY most recent messages.

    Called after settings parsing and noise filtering are complete, so no
    settings data or relevant conversation context is lost by trimming.
    After this point channel_history is always bounded to MAX_HISTORY,
    and prepare_messages_for_api() can send all stored messages directly.

    Args:
        channel_id: Discord channel ID to trim

    Returns:
        dict: Trim operation results with original/final/removed counts
    """
    history = channel_history.get(channel_id, [])
    original_count = len(history)

    if original_count <= MAX_HISTORY:
        logger.debug(
            f"No trim needed for channel {channel_id}: "
            f"{original_count} messages <= MAX_HISTORY={MAX_HISTORY}"
        )
        return {
            'original_count': original_count,
            'final_count': original_count,
            'removed_count': 0
        }

    channel_history[channel_id] = history[-MAX_HISTORY:]
    final_count = len(channel_history[channel_id])
    removed_count = original_count - final_count

    logger.info(
        f"Trimmed channel {channel_id} history: "
        f"{original_count} → {final_count} messages (MAX_HISTORY={MAX_HISTORY})"
    )

    return {
        'original_count': original_count,
        'final_count': final_count,
        'removed_count': removed_count
    }


async def _perform_final_validation(channel):
    """
    Perform final validation and generate statistics for loaded history.

    Args:
        channel: Discord channel object that was processed

    Returns:
        dict: Validation results with message count and any issues found
    """
    channel_id = channel.id
    channel_name = channel.name

    logger.debug(f"Performing final validation for channel #{channel_name}")

    final_message_count = len(channel_history.get(channel_id, []))
    validation_issues = []

    if final_message_count == 0:
        validation_issues.append("No messages in final history")

    if channel_id not in channel_history:
        validation_issues.append("Channel not found in channel_history")

    if channel_id in channel_history:
        for i, msg in enumerate(channel_history[channel_id][:5]):
            if not isinstance(msg, dict):
                validation_issues.append(f"Message {i} is not a dictionary")
            elif 'role' not in msg:
                validation_issues.append(f"Message {i} missing 'role' field")
            elif 'content' not in msg:
                validation_issues.append(f"Message {i} missing 'content' field")

    if validation_issues:
        logger.warning(
            f"Final validation found issues for channel #{channel_name}: "
            f"{validation_issues}"
        )
    else:
        logger.debug(f"Final validation passed for channel #{channel_name}")

    logger.info(
        f"Final validation complete for channel #{channel_name}: "
        f"{final_message_count} messages, {len(validation_issues)} issues"
    )

    return {
        'message_count': final_message_count,
        'validation_issues': validation_issues
    }


def _generate_history_statistics(channel_id):
    """Generate basic statistics for validation reporting."""
    return {
        'total_messages': len(channel_history.get(channel_id, [])),
        'note': 'detailed statistics removed for code optimization'
    }
