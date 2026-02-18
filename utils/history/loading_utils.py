# utils/history/loading_utils.py
# Version 1.2.0
"""
Core utility functions for Discord message history loading operations.

CHANGES v1.2.0: Dead code cleanup (SOW v2.16.0)
- REMOVED: get_loading_status_for_channel() backward compat alias
- REMOVED: force_reload_for_channel() backward compat alias
- REMOVED: get_system_statistics() backward compat alias
- REMOVED: get_loading_system_health() unused utility function
- REMOVED: get_channel_diagnostics() wrapper (diagnostics module imported directly)

CHANGES v1.1.0: Extracted diagnostic functions for maintainability
- Moved get_channel_diagnostics(), identify_potential_issues(),
  estimate_memory_usage() to diagnostics.py
"""
from utils.logging_utils import get_logger
from .storage import loaded_history_channels, channel_history
from .prompts import channel_system_prompts

logger = get_logger('history.loading_utils')

def get_loading_status(channel_id):
    """
    Get comprehensive loading status information for a channel.

    Args:
        channel_id: Discord channel ID to check

    Returns:
        dict: Detailed status information with keys:
            - 'loaded': bool indicating if history is loaded
            - 'timestamp': datetime when history was loaded (if loaded)
            - 'message_count': number of messages in history
            - 'has_custom_prompt': whether channel has custom system prompt
            - 'load_duration': time since loading (if loaded)
    """
    from .storage import is_channel_history_loaded
    import datetime

    is_loaded = is_channel_history_loaded(channel_id)
    timestamp = loaded_history_channels.get(channel_id)
    message_count = len(channel_history.get(channel_id, []))
    has_custom_prompt = channel_id in channel_system_prompts

    load_duration = None
    if timestamp:
        try:
            if isinstance(timestamp, str):
                timestamp = datetime.datetime.fromisoformat(timestamp)
            load_duration = datetime.datetime.now() - timestamp
        except Exception as e:
            logger.debug(f"Error calculating load duration: {e}")

    return {
        'loaded': is_loaded,
        'timestamp': timestamp,
        'message_count': message_count,
        'has_custom_prompt': has_custom_prompt,
        'load_duration': load_duration
    }

def force_reload_channel_history(channel_id):
    """
    Force a channel to be reloaded by removing it from the loaded channels list.

    Args:
        channel_id: Discord channel ID to force reload

    Returns:
        dict: Information about the reload operation
    """
    was_loaded = channel_id in loaded_history_channels
    previous_message_count = len(channel_history.get(channel_id, []))

    if was_loaded:
        del loaded_history_channels[channel_id]
        logger.info(f"Marked channel {channel_id} for forced reload (had {previous_message_count} messages)")
        marked_for_reload = True
    else:
        logger.debug(f"Channel {channel_id} was not loaded, no action taken")
        marked_for_reload = False

    return {
        'was_loaded': was_loaded,
        'previous_message_count': previous_message_count,
        'marked_for_reload': marked_for_reload
    }

def get_history_statistics():
    """
    Get comprehensive statistics about all loaded channel histories.

    Returns:
        dict: System-wide statistics
    """
    from .diagnostics import estimate_memory_usage

    total_channels = len(loaded_history_channels)

    if total_channels == 0:
        return {
            'total_channels': 0,
            'total_messages': 0,
            'average_messages': 0,
            'channels_with_settings': 0,
            'largest_channel': None,
            'smallest_channel': None,
            'memory_usage_estimate': estimate_memory_usage(0)
        }

    channel_message_counts = {}
    total_messages = 0

    for channel_id in loaded_history_channels:
        message_count = len(channel_history.get(channel_id, []))
        channel_message_counts[channel_id] = message_count
        total_messages += message_count

    average_messages = total_messages / total_channels if total_channels > 0 else 0

    largest_channel = None
    smallest_channel = None

    if channel_message_counts:
        largest_count = max(channel_message_counts.values())
        smallest_count = min(channel_message_counts.values())

        largest_channel = {
            'channel_id': next(cid for cid, count in channel_message_counts.items() if count == largest_count),
            'message_count': largest_count
        }

        smallest_channel = {
            'channel_id': next(cid for cid, count in channel_message_counts.items() if count == smallest_count),
            'message_count': smallest_count
        }

    memory_usage_estimate = estimate_memory_usage(total_messages)
    channels_with_settings = len(channel_system_prompts)

    logger.debug(f"Generated system statistics: {total_channels} channels, {total_messages} total messages")

    return {
        'total_channels': total_channels,
        'total_messages': total_messages,
        'average_messages': round(average_messages, 1),
        'channels_with_settings': channels_with_settings,
        'largest_channel': largest_channel,
        'smallest_channel': smallest_channel,
        'memory_usage_estimate': memory_usage_estimate
    }

def get_channel_diagnostics(channel_id):
    """
    Get diagnostic information for a specific channel.
    Delegates to diagnostics module.
    """
    from .diagnostics import get_channel_diagnostics as _get_channel_diagnostics
    return _get_channel_diagnostics(channel_id)
