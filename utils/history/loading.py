"""
Discord message history loading functionality.
"""
import asyncio
import datetime
from config import INITIAL_HISTORY_LOAD, CHANNEL_LOCK_TIMEOUT
from utils.logging_utils import get_logger
from .storage import (
    get_or_create_channel_lock, is_channel_history_loaded, 
    mark_channel_history_loaded, add_message_to_history
)
from .message_processing import (
    should_skip_message_from_history, create_user_message, 
    create_assistant_message, create_system_update_message,
    extract_system_prompt_updates, is_bot_command
)
from .prompts import channel_system_prompts

logger = get_logger('history.loading')

async def load_channel_history(channel, is_automatic=False):
    """
    Load recent message history from a channel with proper locking
    
    Args:
        channel: The Discord channel to load history from
        is_automatic: Whether this is an automatic load (triggered by new message)
        
    Returns:
        None
    """
    channel_id = channel.id
    channel_name = channel.name
    
    logger.debug(f"load_channel_history called for channel #{channel_name} ({channel_id})")
    logger.debug(f"Is channel in loaded_history_channels? {is_channel_history_loaded(channel_id)}")
    if is_automatic:
        logger.debug(f"This is an automatic history load (will skip newest message)")
    
    # Skip if we've already loaded history for this channel
    if is_channel_history_loaded(channel_id):
        logger.debug(f"Channel already in loaded_history_channels, returning early")
        return
    
    # Get or create a lock for this channel
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
            await _load_messages_from_discord(channel, is_automatic)
            
            # Mark channel as loaded only after successful loading
            timestamp = datetime.datetime.now()
            mark_channel_history_loaded(channel_id, timestamp)
            
        except Exception as e:
            logger.error(f"Error loading channel history: {str(e)}")
            # We don't mark the channel as loaded if loading fails
        
        finally:
            # Always release the lock, even if loading fails
            logger.debug(f"Releasing lock for channel #{channel_name}")
            channel_lock.release()
    
    except asyncio.TimeoutError:
        logger.warning(f"Timeout waiting for lock on channel {channel_id}")
        logger.debug(f"Timeout after {CHANNEL_LOCK_TIMEOUT} seconds waiting for lock")

async def _load_messages_from_discord(channel, is_automatic):
    """
    Internal function to load messages from Discord API
    
    Args:
        channel: Discord channel object
        is_automatic: Whether this is automatic loading
    """
    channel_id = channel.id
    channel_name = channel.name
    
    logger.info(f"Loading message history for channel #{channel_name} ({channel_id})")
    
    messages = []
    
    # Fetch recent messages from the channel
    logger.debug(f"Fetching up to {INITIAL_HISTORY_LOAD} messages from Discord API")
    
    # Flag to skip the first message if automatic loading
    should_skip_first = is_automatic
    
    message_count = 0
    skipped_count = 0
    
    # Track if we've found a setprompt command and its response
    found_setprompt = False
    found_setprompt_response = False
    setprompt_content = ""
    
    async for message in channel.history(limit=INITIAL_HISTORY_LOAD):
        message_count += 1
        
        logger.debug(f"Message {message_count}: {message.content[:80]}...")
        
        # Skip the first message if automatic loading
        if should_skip_first:
            should_skip_first = False
            skipped_count += 1
            logger.debug(f"Skipping newest message to avoid duplicate during automatic loading")
            continue
        
        # Special handling for setprompt commands and their responses
        if message.content.startswith('!setprompt '):
            found_setprompt = True
            # Extract the prompt from the command
            setprompt_content = message.content[len('!setprompt '):].strip()
            logger.debug(f"Found !setprompt command with content: {setprompt_content}")
            # Continue to process more messages before deciding what to do
        
        # Check for system prompt update confirmation messages
        if message.author == channel.guild.me and "System prompt updated for" in message.content:
            found_setprompt_response = True
            logger.debug(f"Found system prompt update confirmation")
            # Continue to process more messages
        
        # Check if we should skip this message
        is_bot_message = message.author == channel.guild.me
        should_skip, skip_reason = should_skip_message_from_history(message, is_bot_message)
        
        if should_skip:
            skipped_count += 1
            logger.debug(f"Skipping message ({skip_reason}): {message.content[:30]}...")
            continue
        
        # Add to our list (in reverse, since Discord returns newest first)
        messages.insert(0, message)
    
    logger.debug(f"Fetched {message_count} messages total")
    logger.debug(f"Skipped {skipped_count} messages")
    logger.debug(f"Kept {len(messages)} messages for processing")
    
    # Handle setprompt command without response
    if found_setprompt and setprompt_content and not found_setprompt_response:
        logger.debug(f"Found setprompt command without response, setting prompt directly: {setprompt_content}")
        
        # Create system prompt update entry
        system_update = create_system_update_message(setprompt_content)
        add_message_to_history(channel_id, system_update)
        
        # Set the prompt directly
        channel_system_prompts[channel_id] = setprompt_content
        
        logger.debug(f"Added system prompt directly: {setprompt_content}")
    
    # Process messages and add to history
    await _process_and_add_messages(channel, messages)

async def _process_and_add_messages(channel, messages):
    """
    Process Discord messages and add them to channel history
    
    Args:
        channel: Discord channel object
        messages: List of Discord message objects
    """
    channel_id = channel.id
    channel_name = channel.name
    
    for message in messages:
        # Skip setprompt commands since we already processed them above
        if message.content.startswith('!setprompt'):
            logger.debug(f"Skipping already processed setprompt command")
            continue
        
        # Process differently based on whether it's from our bot or a user
        if message.author == channel.guild.me:
            # Handle system prompt update messages
            if "System prompt updated for" in message.content and "New prompt:" in message.content:
                system_update = _extract_prompt_from_update_message(message)
                if system_update:
                    add_message_to_history(channel_id, system_update)
                    logger.debug(f"Added system prompt update to history")
                    continue
            
            # Regular bot message
            bot_message = create_assistant_message(message.content)
            add_message_to_history(channel_id, bot_message)
            
        else:
            # Process user messages
            user_message = create_user_message(
                message.author.display_name, 
                message.content, 
                len(messages)  # Use as fallback for clean naming
            )
            add_message_to_history(channel_id, user_message)
        
        # Log progress every 10 messages
        current_history = len([msg for msg in messages if msg])  # Simple count
        if current_history % 10 == 0:
            logger.debug(f"Processed {current_history} messages so far")
    
    # Final cleanup and system prompt restoration
    await _finalize_history_loading(channel)

def _extract_prompt_from_update_message(message):
    """
    Extract system prompt from a "System prompt updated" message
    
    Args:
        message: Discord message object
        
    Returns:
        dict or None: System update message dict, or None if extraction failed
    """
    try:
        # Extract the prompt from the confirmation message
        prompt_text = message.content.split("New prompt:", 1)[1].strip()
        # Remove any formatting (like ** for bold)
        prompt_text = prompt_text.replace("**", "").strip()
        
        logger.debug(f"Extracted prompt from update message: {prompt_text}")
        
        # Create system prompt update message
        timestamp = message.created_at.isoformat() if hasattr(message, 'created_at') else datetime.datetime.now().isoformat()
        return create_system_update_message(prompt_text, timestamp)
        
    except Exception as e:
        logger.debug(f"Error extracting prompt from update message: {e}")
        return None

async def _finalize_history_loading(channel):
    """
    Finalize history loading with cleanup and system prompt restoration
    
    Args:
        channel: Discord channel object
    """
    channel_id = channel.id
    channel_name = channel.name
    
    from .storage import channel_history, filter_channel_history
    
    # Perform final cleanup to remove any command messages that slipped through
    original_count, filtered_count, removed_count = filter_channel_history(
        channel_id, 
        lambda msg: not (msg["role"] == "user" and is_bot_command(msg["content"]) and not msg["content"].startswith('!setprompt'))
    )
    
    logger.debug(f"Final cleanup: removed {removed_count} command messages")
    
    # Look for and restore system prompt updates
    system_updates = extract_system_prompt_updates(channel_history[channel_id])
    
    logger.debug(f"Found {len(system_updates)} system prompt updates in history")
    for i, update in enumerate(system_updates):
        logger.debug(f"  Update {i+1}: {update['content'][:100]}...")
    
    if system_updates:
        # Get the most recent update
        latest_update = system_updates[-1]
        
        # Extract the prompt (remove the prefix)
        prompt_text = latest_update["content"].replace("SYSTEM_PROMPT_UPDATE:", "", 1).strip()
        
        # Restore the prompt
        channel_system_prompts[channel_id] = prompt_text
        logger.debug(f"Restored custom system prompt: {prompt_text[:100]}...")
        logger.info(f"Restored custom system prompt for channel #{channel_name}")
    
    logger.info(f"Loaded {len(channel_history[channel_id])} messages for channel #{channel_name}")
