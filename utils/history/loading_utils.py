# utils/history/loading_utils.py
# Version 1.1.0
"""
Core utility functions for Discord message history loading operations.

CHANGES v1.1.0: Extracted diagnostic functions for maintainability
- Moved get_channel_diagnostics() to diagnostics.py
- Moved identify_potential_issues() to diagnostics.py  
- Moved estimate_memory_usage() to diagnostics.py
- Reduced file size from 291 to under 200 lines
- Maintained all core loading utilities and backward compatibility

This module provides essential utility functions that support the history loading
system but are not part of the core coordination workflow. These functions handle
status checking, forced reloading, statistics generation, and health monitoring.

Key Responsibilities:
- Provide status information about loaded channels
- Enable forced reloading of channel history for debugging/testing
- Generate system-wide statistics about the history loading system
- Support external monitoring and management of the loading system
- Maintain backward compatibility with existing code

Core utilities are kept here while diagnostic tools have been moved to
diagnostics.py to maintain clean separation of concerns and file size limits.
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
    
    # Get memory usage estimate from diagnostics module
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

def get_loading_system_health():
    """
    Get overall health status of the history loading system.
    
    Returns:
        dict: Health information about the loading system with keys:
            - 'status': overall health status (healthy/warning/error)
            - 'issues': list of identified issues
            - 'summary': summary statistics about the system
    """
    try:
        stats = get_history_statistics()
        
        # Determine health based on statistics
        health_status = "healthy"
        issues = []
        
        if stats['total_channels'] == 0:
            health_status = "warning"
            issues.append("No channels loaded")
        
        if stats['total_messages'] == 0:
            health_status = "warning" 
            issues.append("No messages in system")
        
        # Check for memory usage concerns
        memory_mb = stats['memory_usage_estimate']['megabytes']
        if memory_mb > 100:  # More than 100MB
            health_status = "warning"
            issues.append(f"High memory usage: {memory_mb}MB")
        
        return {
            'status': health_status,
            'issues': issues,
            'summary': {
                'channels_loaded': stats['total_channels'],
                'total_messages': stats['total_messages'],
                'average_per_channel': stats['average_messages'],
                'memory_usage_mb': memory_mb
            }
        }
        
    except Exception as e:
        logger.error(f"Error checking loading system health: {e}")
        return {
            'status': 'error',
            'issues': [f"Health check failed: {str(e)}"],
            'summary': None
        }

# Backward compatibility aliases for existing code
def get_loading_status_for_channel(channel_id):
    """Backward compatibility alias for get_loading_status."""
    return get_loading_status(channel_id)

def force_reload_for_channel(channel_id):
    """Backward compatibility alias for force_reload_channel_history."""
    return force_reload_channel_history(channel_id)

def get_system_statistics():
    """Backward compatibility alias for get_history_statistics."""
    return get_history_statistics()

# Import diagnostic functions for backward compatibility
def get_channel_diagnostics(channel_id):
    """Backward compatibility wrapper for diagnostics module."""
    from .diagnostics import get_channel_diagnostics as _get_channel_diagnostics
    return _get_channel_diagnostics(channel_id)
