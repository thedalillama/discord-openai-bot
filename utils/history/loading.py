# utils/history/loading.py
# Version 2.1.1
"""
Discord message history loading coordination and public interface.

This module provides the main coordination layer for loading Discord message history.
It orchestrates the interaction between Discord API loading, message processing,
settings restoration, and final cleanup operations.

CHANGES v2.1.1: Fixed import - validate_parsed_settings is in settings_manager, not settings_parser
CHANGES v2.1.0: Updated imports for settings_parser and settings_manager split
CHANGES v2.0.0: Major refactoring to split functionality into focused modules:
- Discord API interactions moved to discord_loader.py  
- Settings restoration functionality moved to settings_parser.py and settings_manager.py
- This module now focuses on coordination, locking, and public interface
- Maintains backward compatibility with existing imports

The loading process follows this flow:
1. Check if channel history already loaded (prevent duplicates)
2. Acquire channel-specific lock (prevent race conditions)
3. Load messages from Discord API (discord_loader.py)
4. Restore configuration settings from history (settings_parser.py + settings_manager.py)
5. Perform final cleanup and validation
6. Mark channel as loaded

This refactoring prepares the codebase for the upcoming Configuration Persistence
feature while improving maintainability and testability.
"""
import asyncio
import datetime
from config import CHANNEL_LOCK_TIMEOUT
from utils.logging_utils import get_logger
from .storage import (
    get_or_create_channel_lock, is_channel_history_loaded, 
    mark_channel_history_loaded, filter_channel_history, channel_history
)
from .message_processing import (
    extract_system_prompt_updates, is_bot_command
)
from .prompts import channel_system_prompts
from .discord_loader import load_messages_from_discord
from .settings_parser import parse_settings_from_history
from .settings_manager import apply_restored_settings, get_restoration_summary, validate_parsed_settings

logger = get_logger('history.loading')

async def load_channel_history(channel, is_automatic=False):
    """
    Load recent message history from a channel with proper locking and coordination.
    
    This is the main public interface for loading channel history. It coordinates
    all aspects of the loading process including Discord API interaction, settings
    restoration, and final cleanup.
    
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
    channel_id = channel.id
    channel_name = channel.name
    
    logger.debug(f"load_channel_history called for channel #{channel_name} ({channel_id})")
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
            channel_lock.release()
            return
        
        try:
            # Perform the actual loading process
            await _perform_history_loading(channel, is_automatic)
            
            # Mark channel as loaded only after successful loading
            timestamp = datetime.datetime.now()
            mark_channel_history_loaded(channel_id, timestamp)
            
            logger.info(f"Successfully completed history loading for channel #{channel_name}")
            
        except Exception as e:
            logger.error(f"Error loading channel history: {str(e)}")
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

async def _perform_history_loading(channel, is_automatic):
    """
    Internal function to perform the complete history loading process.
    
    This function coordinates all the steps of history loading:
    1. Load messages from Discord API
    2. Restore configuration settings from history  
    3. Perform final cleanup and validation
    
    Args:
        channel: Discord channel object
        is_automatic: Whether this is automatic loading
        
    Raises:
        Exception: If any step of the loading process fails
    """
    channel_id = channel.id
    channel_name = channel.name
    
    logger.info(f"Starting complete history loading process for channel #{channel_name} ({channel_id})")
    
    # Step 1: Load messages from Discord API
    try:
        processed_count, skipped_count = await load_messages_from_discord(channel, is_automatic)
        logger.info(f"Discord loading complete: {processed_count} processed, {skipped_count} skipped")
        
    except Exception as e:
        logger.error(f"Failed to load messages from Discord: {e}")
        raise
    
    # Step 2: Restore configuration settings from the loaded history
    try:
        await _restore_channel_settings(channel_id)
        
    except Exception as e:
        logger.error(f"Failed to restore settings from history: {e}")
        # Settings restoration failure shouldn't stop history loading
        logger.warning("Continuing with history loading despite settings restoration failure")
    
    # Step 3: Perform final cleanup and validation
    try:
        await _finalize_history_loading(channel)
        
    except Exception as e:
        logger.error(f"Failed to finalize history loading: {e}")
        raise
    
    logger.info(f"Complete history loading process finished for channel #{channel_name}")

async def _restore_channel_settings(channel_id):
    """
    Restore channel configuration settings from loaded conversation history.
    
    This function implements the Configuration Persistence feature by parsing
    the loaded conversation history to extract and restore channel settings.
    
    Args:
        channel_id: Discord channel ID to restore settings for
        
    Returns:
        dict: Summary of restoration results
    """
    logger.debug(f"Starting settings restoration for channel {channel_id}")
    
    # Get the loaded history for this channel
    if channel_id not in channel_history:
        logger.debug(f"No history loaded for channel {channel_id}, skipping settings restoration")
        return {'applied': [], 'skipped': [], 'errors': ['No history available']}
    
    history_messages = channel_history[channel_id]
    
    if not history_messages:
        logger.debug(f"Empty history for channel {channel_id}, skipping settings restoration")
        return {'applied': [], 'skipped': [], 'errors': ['History is empty']}
    
    # Parse settings from the conversation history
    try:
        settings = parse_settings_from_history(history_messages, channel_id)
        
        # Validate the parsed settings
        is_valid, validation_errors = validate_parsed_settings(settings)
        
        if not is_valid:
            logger.warning(f"Settings validation failed for channel {channel_id}: {validation_errors}")
            return {'applied': [], 'skipped': [], 'errors': validation_errors}
        
        # Apply the validated settings
        result = apply_restored_settings(settings, channel_id)
        
        # Log restoration summary
        if result['applied']:
            summary = get_restoration_summary(settings)
            logger.info(f"Settings restored for channel {channel_id}: {summary}")
        else:
            logger.debug(f"No settings to restore for channel {channel_id}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error during settings restoration for channel {channel_id}: {e}")
        return {'applied': [], 'skipped': [], 'errors': [str(e)]}

async def _finalize_history_loading(channel):
    """
    Finalize history loading with cleanup and legacy system prompt restoration.
    
    This function performs final cleanup operations and handles legacy system
    prompt restoration for backward compatibility.
    
    Args:
        channel: Discord channel object
    """
    channel_id = channel.id
    channel_name = channel.name
    
    logger.debug(f"Finalizing history loading for channel #{channel_name}")
    
    # Perform final cleanup to remove any command messages that slipped through
    original_count, filtered_count, removed_count = filter_channel_history(
        channel_id, 
        lambda msg: not (msg["role"] == "user" and is_bot_command(msg["content"]) and not msg["content"].startswith('!setprompt'))
    )
    
    if removed_count > 0:
        logger.debug(f"Final cleanup: removed {removed_count} command messages")
    
    # Legacy system prompt restoration (backward compatibility)
    # This handles the old SYSTEM_PROMPT_UPDATE format for channels that haven't
    # been processed by the new settings restoration system
    if channel_id not in channel_system_prompts:
        await _legacy_system_prompt_restoration(channel_id)
    
    final_message_count = len(channel_history[channel_id])
    logger.info(f"History loading finalized for channel #{channel_name}: {final_message_count} total messages")

async def _legacy_system_prompt_restoration(channel_id):
    """
    Legacy system prompt restoration for backward compatibility.
    
    This function handles the old system prompt restoration logic for channels
    that don't have settings restored by the new system. It will be deprecated
    once all channels have been processed by the new settings restoration.
    
    Args:
        channel_id: Discord channel ID to restore legacy settings for
    """
    logger.debug(f"Performing legacy system prompt restoration for channel {channel_id}")
    
    try:
        # Look for and restore system prompt updates using the old method
        system_updates = extract_system_prompt_updates(channel_history[channel_id])
        
        logger.debug(f"Found {len(system_updates)} legacy system prompt updates")
        
        if system_updates:
            # Get the most recent update
            latest_update = system_updates[-1]
            
            # Extract the prompt (remove the prefix)
            prompt_text = latest_update["content"].replace("SYSTEM_PROMPT_UPDATE:", "", 1).strip()
            
            # Restore the prompt
            channel_system_prompts[channel_id] = prompt_text
            logger.info(f"Restored legacy system prompt for channel {channel_id}: {prompt_text[:50]}...")
        else:
            logger.debug(f"No legacy system prompt updates found for channel {channel_id}")
            
    except Exception as e:
        logger.error(f"Error during legacy system prompt restoration for channel {channel_id}: {e}")

# Utility functions for external use

def get_loading_status(channel_id):
    """
    Get the loading status for a channel.
    
    Args:
        channel_id: Discord channel ID
        
    Returns:
        dict: Status information with keys:
            - 'loaded': bool indicating if history is loaded
            - 'timestamp': datetime when history was loaded (if loaded)
            - 'message_count': number of messages in history
    """
    from .storage import loaded_history_channels
    
    return {
        'loaded': is_channel_history_loaded(channel_id),
        'timestamp': loaded_history_channels.get(channel_id),
        'message_count': len(channel_history.get(channel_id, []))
    }

def force_reload_channel_history(channel_id):
    """
    Force a channel to be reloaded by removing it from the loaded channels list.
    
    This is useful for testing or when you want to force a fresh load of history.
    
    Args:
        channel_id: Discord channel ID to force reload
        
    Returns:
        bool: True if channel was marked for reload, False if it wasn't loaded
    """
    from .storage import loaded_history_channels
    
    if channel_id in loaded_history_channels:
        del loaded_history_channels[channel_id]
        logger.info(f"Marked channel {channel_id} for forced reload")
        return True
    else:
        logger.debug(f"Channel {channel_id} was not loaded, no action taken")
        return False

def get_history_statistics():
    """
    Get statistics about loaded channel histories.
    
    Returns:
        dict: Statistics with keys:
            - 'total_channels': number of channels with loaded history
            - 'total_messages': total messages across all channels
            - 'average_messages': average messages per channel
            - 'channels_with_settings': number of channels with custom settings
    """
    from .storage import loaded_history_channels
    
    total_channels = len(loaded_history_channels)
    total_messages = sum(len(channel_history.get(cid, [])) for cid in loaded_history_channels)
    average_messages = total_messages / total_channels if total_channels > 0 else 0
    channels_with_settings = len(channel_system_prompts)
    
    return {
        'total_channels': total_channels,
        'total_messages': total_messages,
        'average_messages': round(average_messages, 1),
        'channels_with_settings': channels_with_settings
    }
