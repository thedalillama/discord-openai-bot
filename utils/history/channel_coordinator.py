# utils/history/channel_coordinator.py
# Version 2.0.0
"""
Channel coordination and locking management for Discord message history loading.

CHANGES v2.0.0: Removed legacy settings restoration
- REMOVED: Legacy post-loading settings restoration (now handled during Discord loading)
- SIMPLIFIED: Loading workflow now focuses on core Discord loading and cleanup
- ELIMINATED: Double-application of settings (prevention of redundancy)

This module handles the high-level coordination of channel history loading,
including concurrency control through channel-specific locking, basic validation,
and delegation to specialized coordinators for different aspects of the loading process.

Key Responsibilities:
- Channel locking to prevent race conditions during loading
- High-level coordination of the loading workflow
- Delegation to specialized coordinators for cleanup
- Error handling and recovery for the overall process
- Public API entry points that other parts of the bot call

Settings are now applied during Discord message discovery via realtime parsing,
eliminating the need for post-loading restoration.
"""
import asyncio
import datetime
from config import CHANNEL_LOCK_TIMEOUT
from utils.logging_utils import get_logger
from .storage import (
    get_or_create_channel_lock, is_channel_history_loaded, 
    mark_channel_history_loaded
)
from .discord_loader import load_messages_from_discord

logger = get_logger('history.channel_coordinator')

async def coordinate_channel_loading(channel, is_automatic=False):
    """
    Coordinate the complete channel history loading process with proper locking.
    
    This is the main coordination function that handles:
    1. Channel loading status validation
    2. Concurrency control through channel-specific locking
    3. Delegation to Discord loading with realtime settings parsing
    4. Final status marking and cleanup
    
    Args:
        channel: The Discord channel to load history from
        is_automatic: Whether this is an automatic load (triggered by new message)
        
    Returns:
        None
        
    Raises:
        asyncio.TimeoutError: If unable to acquire channel lock within timeout
        Exception: If any step of the loading process fails
    """
    channel_id = channel.id
    channel_name = channel.name
    
    logger.debug(f"coordinate_channel_loading called for channel #{channel_name} ({channel_id})")
    logger.debug(f"Is channel in loaded_history_channels? {is_channel_history_loaded(channel_id)}")
    logger.debug(f"Automatic loading: {is_automatic}")
    
    # Skip if we've already loaded history for this channel
    if is_channel_history_loaded(channel_id):
        logger.debug(f"Channel already in loaded_history_channels, returning early")
        return
    
    # Get or create a lock for this channel to prevent race conditions
    channel_lock = get_or_create_channel_lock(channel_id, channel_name)
    
    try:
        logger.debug(f"Attempting to acquire lock for channel #{channel_name}")
        
        # Wait up to CHANNEL_LOCK_TIMEOUT seconds to acquire the lock
        await asyncio.wait_for(channel_lock.acquire(), timeout=CHANNEL_LOCK_TIMEOUT)
        
        logger.debug(f"Successfully acquired lock for channel #{channel_name}")
        
        # Double check if history was loaded while we were waiting for the lock
        if is_channel_history_loaded(channel_id):
            logger.debug(f"Channel was added to loaded_history_channels while waiting for lock, returning early")
            return
        
        try:
            # Perform the actual loading process using simplified workflow
            await _execute_loading_workflow(channel, is_automatic)
            
            # Mark channel as loaded only after successful loading
            timestamp = datetime.datetime.now()
            mark_channel_history_loaded(channel_id, timestamp)
            
            logger.info(f"Successfully completed history loading for channel #{channel_name}")
            
        except Exception as e:
            logger.error(f"Error in loading workflow: {str(e)}")
            # We don't mark the channel as loaded if loading fails
            raise
        
        finally:
            # Always release the lock, even if loading fails
            logger.debug(f"Releasing lock for channel #{channel_name}")
            channel_lock.release()
    
    except asyncio.TimeoutError:
        logger.warning(f"Timeout waiting for lock on channel {channel_id}")
        logger.debug(f"Timeout after {CHANNEL_LOCK_TIMEOUT} seconds waiting for lock")
        raise

async def _execute_loading_workflow(channel, is_automatic):
    """
    Execute the simplified loading workflow with realtime settings parsing.
    
    This function orchestrates the loading process using the simplified architecture
    where settings are applied during Discord message discovery, eliminating the need
    for post-loading restoration.
    
    Args:
        channel: Discord channel object
        is_automatic: Whether this is automatic loading
        
    Raises:
        Exception: If any critical step of the loading process fails
    """
    channel_id = channel.id
    channel_name = channel.name
    
    logger.info(f"Starting simplified loading workflow for channel #{channel_name} ({channel_id})")
    
    # Step 1: Load messages from Discord API with realtime settings parsing
    # This handles: fetch → real-time settings parsing → message conversion
    try:
        processed_count, skipped_count = await load_messages_from_discord(channel, is_automatic)
        logger.info(f"Discord loading complete: {processed_count} processed, {skipped_count} skipped")
        
    except Exception as e:
        logger.error(f"Failed to load messages from Discord: {e}")
        raise
    
    # Step 2: Final cleanup and validation (optional)
    try:
        from .cleanup_coordinator import coordinate_final_cleanup
        cleanup_result = await coordinate_final_cleanup(channel)
        
        logger.debug(f"Final cleanup complete: {cleanup_result}")
        
    except Exception as e:
        logger.error(f"Failed to complete final cleanup: {e}")
        # Cleanup failure shouldn't stop history loading
        logger.warning("Continuing with history loading despite cleanup issues")
    
    logger.info(f"Simplified loading workflow completed successfully for channel #{channel_name}")

def validate_channel_for_loading(channel):
    """
    Validate that a channel is suitable for history loading.
    
    Performs basic validation checks to ensure the channel can be processed
    for history loading.
    
    Args:
        channel: Discord channel object to validate
        
    Returns:
        tuple: (is_valid, error_message)
            is_valid: bool indicating if channel is valid for loading
            error_message: str describing validation failure, None if valid
    """
    if not channel:
        return False, "Channel object is None"
    
    if not hasattr(channel, 'id'):
        return False, "Channel missing id attribute"
    
    if not hasattr(channel, 'name'):
        return False, "Channel missing name attribute"
    
    if not hasattr(channel, 'history'):
        return False, "Channel missing history method"
    
    return True, None
