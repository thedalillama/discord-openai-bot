# utils/history/loading.py
# Version 2.4.0
"""
Discord message history loading - main public interface.

CHANGES v2.4.0: Dead code cleanup (SOW v2.16.0)
- REMOVED: get_loading_status_for_channel() backward compat alias
- REMOVED: force_reload_for_channel() backward compat alias
- REMOVED: get_system_statistics() backward compat alias
- REMOVED: get_loading_system_health() unused utility function

CHANGES v2.3.0: Major refactoring to split functionality into focused coordinators
- Delegates to channel_coordinator.py for locking and workflow coordination
- Imports utility functions from loading_utils.py
- Reduced from 361 lines to under 50 lines
- Maintains exact same public API for backward compatibility
"""
from utils.logging_utils import get_logger
from .channel_coordinator import coordinate_channel_loading
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

    Args:
        channel: The Discord channel to load history from
        is_automatic: Whether this is an automatic load (triggered by new message)

    Returns:
        None

    Raises:
        asyncio.TimeoutError: If unable to acquire channel lock within timeout
        Exception: If Discord API calls or processing fails
    """
    logger.debug(f"Public API load_channel_history called for channel #{channel.name}")
    await coordinate_channel_loading(channel, is_automatic)
    logger.debug(f"Public API load_channel_history completed for channel #{channel.name}")
