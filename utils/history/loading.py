# utils/history/loading.py
# Version 2.3.0
"""
Discord message history loading - main public interface.

This module provides the main public interface for Discord message history loading.
It delegates to specialized coordinators while maintaining backward compatibility
with existing code that calls the loading functions.

CHANGES v2.3.0: Major refactoring to split functionality into focused coordinators
- Delegates to channel_coordinator.py for locking and workflow coordination
- Imports utility functions from loading_utils.py 
- Reduced from 361 lines (v2.1.1) to under 50 lines
- Maintains exact same public API for backward compatibility
- Enhanced with modular architecture for better maintainability

The refactored architecture splits the original large file into:
- channel_coordinator.py: Channel locking and workflow coordination
- settings_coordinator.py: Settings restoration coordination  
- cleanup_coordinator.py: Final cleanup and validation
- loading_utils.py: Utility functions for status and diagnostics
- This file: Simple public API that delegates to coordinators

All existing code that imports from this module will continue to work unchanged.
"""
from utils.logging_utils import get_logger

# Import main coordination function
from .channel_coordinator import coordinate_channel_loading

# Import utility functions
from .loading_utils import (
    get_loading_status,
    force_reload_channel_history, 
    get_history_statistics,
    get_channel_diagnostics
)

logger = get_logger('history.loading')

async def load_channel_history(channel, is_automatic=False):
    """
    Load recent message history from a channel with proper coordination.
    
    This is the main public interface for loading channel history. It delegates
    to the channel coordinator while maintaining the exact same API that existing
    code expects.
    
    Args:
        channel: The Discord channel to load history from
        is_automatic: Whether this is an automatic load (triggered by new message)
        
    Returns:
        None
        
    Raises:
        asyncio.TimeoutError: If unable to acquire channel lock within timeout
        Exception: If Discord API calls or processing fails
        
    Example:
        await load_channel_history(channel, is_automatic=True)
    """
    logger.debug(f"Public API load_channel_history called for channel #{channel.name}")
    
    # Delegate to the channel coordinator for actual work
    await coordinate_channel_loading(channel, is_automatic)
    
    logger.debug(f"Public API load_channel_history completed for channel #{channel.name}")

# Re-export utility functions for backward compatibility
# These maintain the exact same function signatures as the original loading.py

def get_loading_status_for_channel(channel_id):
    """
    Backward compatibility alias for get_loading_status.
    
    Args:
        channel_id: Discord channel ID
        
    Returns:
        dict: Status information about the channel's loading state
    """
    return get_loading_status(channel_id)

def force_reload_for_channel(channel_id):
    """
    Backward compatibility alias for force_reload_channel_history.
    
    Args:
        channel_id: Discord channel ID to force reload
        
    Returns:
        dict: Information about the reload operation
    """
    return force_reload_channel_history(channel_id)

def get_system_statistics():
    """
    Backward compatibility alias for get_history_statistics.
    
    Returns:
        dict: System-wide statistics about loaded histories
    """
    return get_history_statistics()

# Additional utility function for external monitoring
def get_loading_system_health():
    """
    Get overall health status of the history loading system.
    
    Returns:
        dict: Health information about the loading system
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
        
        return {
            'status': health_status,
            'issues': issues,
            'summary': {
                'channels_loaded': stats['total_channels'],
                'total_messages': stats['total_messages'],
                'average_per_channel': stats['average_messages']
            }
        }
        
    except Exception as e:
        logger.error(f"Error checking loading system health: {e}")
        return {
            'status': 'error',
            'issues': [f"Health check failed: {str(e)}"],
            'summary': None
        }
