# utils/history/loading_utils.py
# Version 1.0.0
"""
Utility functions for Discord message history loading operations.

This module provides utility functions that support the history loading system
but are not part of the core coordination workflow. These functions handle
status checking, forced reloading, statistics generation, and other helper
operations that external code might need.

Key Responsibilities:
- Provide status information about loaded channels
- Enable forced reloading of channel history for debugging/testing
- Generate comprehensive statistics about the history loading system
- Offer diagnostic tools for troubleshooting loading issues
- Support external monitoring and management of the loading system

These utilities are separated from the main loading coordination to keep
the core workflow focused and to provide a clean interface for external
systems that need to interact with or monitor the history loading system.

Created in refactoring to maintain under 200-line limit while preserving
all utility functionality from the original loading.py.
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
    
    # Calculate load duration if available
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
    
    This is useful for testing, debugging, or when you want to force a fresh
    load of history (for example, after manual database changes or for
    troubleshooting loading issues).
    
    Args:
        channel_id: Discord channel ID to force reload
        
    Returns:
        dict: Information about the reload operation:
            - 'was_loaded': bool indicating if channel was previously loaded
            - 'previous_message_count': number of messages before reload
            - 'marked_for_reload': bool indicating successful marking
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
        dict: System-wide statistics with keys:
            - 'total_channels': number of channels with loaded history
            - 'total_messages': total messages across all channels
            - 'average_messages': average messages per channel
            - 'channels_with_settings': number of channels with custom settings
            - 'largest_channel': info about channel with most messages
            - 'smallest_channel': info about channel with fewest messages
            - 'memory_usage_estimate': rough estimate of memory usage
    """
    total_channels = len(loaded_history_channels)
    
    if total_channels == 0:
        return {
            'total_channels': 0,
            'total_messages': 0,
            'average_messages': 0,
            'channels_with_settings': 0,
            'largest_channel': None,
            'smallest_channel': None,
            'memory_usage_estimate': 0
        }
    
    # Collect per-channel statistics
    channel_message_counts = {}
    total_messages = 0
    
    for channel_id in loaded_history_channels:
        message_count = len(channel_history.get(channel_id, []))
        channel_message_counts[channel_id] = message_count
        total_messages += message_count
    
    average_messages = total_messages / total_channels if total_channels > 0 else 0
    
    # Find largest and smallest channels
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
    
    # Estimate memory usage (rough calculation)
    memory_usage_estimate = _estimate_memory_usage(total_messages)
    
    channels_with_settings = len(channel_system_prompts)
    
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
    Get detailed diagnostic information about a specific channel's history.
    
    This function provides comprehensive diagnostic information useful for
    troubleshooting loading issues or understanding the state of a channel's
    conversation history.
    
    Args:
        channel_id: Discord channel ID to diagnose
        
    Returns:
        dict: Detailed diagnostic information
    """
    diagnostics = {
        'channel_id': channel_id,
        'is_loaded': channel_id in loaded_history_channels,
        'load_timestamp': loaded_history_channels.get(channel_id),
        'message_count': len(channel_history.get(channel_id, [])),
        'has_custom_prompt': channel_id in channel_system_prompts,
        'message_roles': {},
        'content_statistics': {},
        'potential_issues': []
    }
    
    # Analyze message content if available
    if channel_id in channel_history:
        messages = channel_history[channel_id]
        
        # Count messages by role
        for msg in messages:
            role = msg.get('role', 'unknown')
            diagnostics['message_roles'][role] = diagnostics['message_roles'].get(role, 0) + 1
        
        # Analyze content
        if messages:
            content_lengths = [len(msg.get('content', '')) for msg in messages]
            diagnostics['content_statistics'] = {
                'average_length': round(sum(content_lengths) / len(content_lengths), 1),
                'max_length': max(content_lengths),
                'min_length': min(content_lengths),
                'total_characters': sum(content_lengths)
            }
        
        # Check for potential issues
        diagnostics['potential_issues'] = _identify_potential_issues(messages)
    
    return diagnostics

def _estimate_memory_usage(total_messages):
    """
    Provide a rough estimate of memory usage for conversation histories.
    
    Args:
        total_messages: Total number of messages across all channels
        
    Returns:
        dict: Memory usage estimate in different units
    """
    # Rough estimates based on typical message sizes
    # Average message: ~200 characters content + ~100 bytes metadata = ~300 bytes
    bytes_per_message = 300
    estimated_bytes = total_messages * bytes_per_message
    
    return {
        'bytes': estimated_bytes,
        'kilobytes': round(estimated_bytes / 1024, 1),
        'megabytes': round(estimated_bytes / (1024 * 1024), 2),
        'note': 'Rough estimate based on average message size'
    }

def _identify_potential_issues(messages):
    """
    Identify potential issues in a channel's conversation history.
    
    Args:
        messages: List of message dicts for a channel
        
    Returns:
        list: List of potential issues found
    """
    issues = []
    
    if not messages:
        issues.append("No messages in history")
        return issues
    
    # Check for format consistency
    for i, msg in enumerate(messages[:10]):  # Check first 10 messages
        if not isinstance(msg, dict):
            issues.append(f"Message {i} is not a dictionary")
        elif 'role' not in msg:
            issues.append(f"Message {i} missing 'role' field")
        elif 'content' not in msg:
            issues.append(f"Message {i} missing 'content' field")
    
    # Check role distribution
    role_counts = {}
    for msg in messages:
        role = msg.get('role', 'unknown')
        role_counts[role] = role_counts.get(role, 0) + 1
    
    if role_counts.get('user', 0) == 0:
        issues.append("No user messages found")
    
    if role_counts.get('assistant', 0) == 0:
        issues.append("No assistant messages found")
    
    # Check for extremely long messages
    for i, msg in enumerate(messages):
        content_length = len(msg.get('content', ''))
        if content_length > 10000:  # Very long message
            issues.append(f"Message {i} is very long ({content_length} characters)")
    
    return issues
