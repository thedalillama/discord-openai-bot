# utils/history/discord_loader.py
# Version 1.0.0
"""
Discord API interaction functionality for message history loading.

This module handles the low-level Discord API interactions for fetching and processing
message history. It's responsible for:
- Fetching messages from Discord channels
- Processing Discord message objects into standardized format
- Handling Discord-specific edge cases and filtering
- Managing setprompt command detection and processing

Separated from loading.py in v2.0.0 refactoring to improve maintainability
and prepare for configuration persistence features.
"""
import datetime
from config import INITIAL_HISTORY_LOAD
from utils.logging_utils import get_logger
from .storage import add_message_to_history
from .message_processing import (
    should_skip_message_from_history, create_user_message, 
    create_assistant_message, create_system_update_message,
    is_bot_command
)
from .prompts import channel_system_prompts

logger = get_logger('history.discord_loader')

async def load_messages_from_discord(channel, is_automatic):
    """
    Load messages from Discord API and process them into standardized format.
    
    This function handles the core Discord API interaction, fetching messages
    and processing them through the message filtering and formatting pipeline.
    
    Args:
        channel: Discord channel object to load messages from
        is_automatic: Whether this is automatic loading (skips newest message to avoid duplicates)
        
    Returns:
        tuple: (processed_messages_count, skipped_messages_count)
        
    Raises:
        Exception: If Discord API calls fail or message processing encounters errors
    """
    channel_id = channel.id
    channel_name = channel.name
    
    logger.info(f"Loading message history from Discord API for channel #{channel_name} ({channel_id})")
    logger.debug(f"Automatic loading: {is_automatic}, will fetch up to {INITIAL_HISTORY_LOAD} messages")
    
    messages = []
    
    # Flag to skip the first message if automatic loading
    should_skip_first = is_automatic
    
    message_count = 0
    skipped_count = 0
    
    # Track if we've found a setprompt command and its response
    found_setprompt = False
    found_setprompt_response = False
    setprompt_content = ""
    
    logger.debug(f"Fetching up to {INITIAL_HISTORY_LOAD} messages from Discord API")
    
    # Fetch messages from Discord API
    async for message in channel.history(limit=INITIAL_HISTORY_LOAD):
        message_count += 1
        
        logger.debug(f"Processing Discord message {message_count}: {message.content[:80]}...")
        
        # Skip the first message if automatic loading to avoid duplicates
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
        
        # Check if we should skip this message based on filtering rules
        is_bot_message = message.author == channel.guild.me
        should_skip, skip_reason = should_skip_message_from_history(message, is_bot_message)
        
        if should_skip:
            skipped_count += 1
            logger.debug(f"Skipping message ({skip_reason}): {message.content[:30]}...")
            continue
        
        # Add to our list (in reverse, since Discord returns newest first)
        messages.insert(0, message)
    
    logger.info(f"Discord API fetch complete: {message_count} total messages, {skipped_count} skipped, {len(messages)} kept for processing")
    
    # Handle setprompt command without response - this preserves system prompts
    # across bot restarts by detecting unprocessed setprompt commands
    if found_setprompt and setprompt_content and not found_setprompt_response:
        logger.info(f"Found unprocessed setprompt command, setting prompt directly: {setprompt_content}")
        
        # Create system prompt update entry for history tracking
        system_update = create_system_update_message(setprompt_content)
        add_message_to_history(channel_id, system_update)
        
        # Set the prompt directly in memory
        channel_system_prompts[channel_id] = setprompt_content
        
        logger.debug(f"Added system prompt directly and recorded in history")
    
    # Process the collected messages
    processed_count = await process_discord_messages(channel, messages)
    
    logger.info(f"Message processing complete: {processed_count} messages added to history")
    
    return processed_count, skipped_count

async def process_discord_messages(channel, messages):
    """
    Process a list of Discord message objects into standardized conversation history format.
    
    This function converts Discord message objects into the standardized message format
    used by AI providers, handling user messages, bot messages, and special system messages.
    
    Args:
        channel: Discord channel object (for bot identity checking)
        messages: List of Discord message objects to process
        
    Returns:
        int: Number of messages successfully processed and added to history
    """
    channel_id = channel.id
    channel_name = channel.name
    processed_count = 0
    
    logger.debug(f"Processing {len(messages)} Discord messages for channel #{channel_name}")
    
    for i, message in enumerate(messages):
        try:
            # Skip setprompt commands since we already processed them in the fetch phase
            if message.content.startswith('!setprompt'):
                logger.debug(f"Skipping already processed setprompt command")
                continue
            
            # Process differently based on whether it's from our bot or a user
            if message.author == channel.guild.me:
                # Handle special system prompt update messages
                if "System prompt updated for" in message.content and "New prompt:" in message.content:
                    system_update = extract_prompt_from_update_message(message)
                    if system_update:
                        add_message_to_history(channel_id, system_update)
                        logger.debug(f"Added system prompt update to history from bot message")
                        processed_count += 1
                        continue
                
                # Regular bot message - convert to assistant format
                bot_message = create_assistant_message(message.content)
                add_message_to_history(channel_id, bot_message)
                processed_count += 1
                
            else:
                # User message - convert to user format with proper naming
                user_message = create_user_message(
                    message.author.display_name, 
                    message.content, 
                    len(messages)  # Use total count as fallback for clean naming
                )
                add_message_to_history(channel_id, user_message)
                processed_count += 1
            
            # Log progress every 10 messages for long histories
            if (i + 1) % 10 == 0:
                logger.debug(f"Processed {i + 1}/{len(messages)} messages")
                
        except Exception as e:
            logger.error(f"Error processing message {i+1}: {e}")
            logger.debug(f"Problematic message content: {message.content[:100]}...")
            # Continue processing other messages even if one fails
            continue
    
    logger.debug(f"Message processing complete: {processed_count} messages successfully processed")
    
    return processed_count

def extract_prompt_from_update_message(message):
    """
    Extract system prompt text from a "System prompt updated" confirmation message.
    
    This function parses bot confirmation messages that contain system prompt updates
    to restore the actual prompt text for history tracking.
    
    Args:
        message: Discord message object containing system prompt update confirmation
        
    Returns:
        dict or None: System update message dict for history, or None if extraction failed
        
    Example:
        Input message: "System prompt updated for #channel. New prompt: **You are helpful**"
        Output: {"role": "system", "content": "SYSTEM_PROMPT_UPDATE: You are helpful", "timestamp": "..."}
    """
    try:
        # Extract the prompt from the confirmation message format
        # Expected format: "System prompt updated for #channel. New prompt: **[prompt text]**"
        if "New prompt:" not in message.content:
            logger.debug(f"System prompt update message missing 'New prompt:' section")
            return None
            
        prompt_text = message.content.split("New prompt:", 1)[1].strip()
        
        # Remove any Discord formatting (like ** for bold)
        prompt_text = prompt_text.replace("**", "").strip()
        
        if not prompt_text:
            logger.debug(f"Extracted prompt text was empty after cleaning")
            return None
        
        logger.debug(f"Successfully extracted prompt from update message: {prompt_text[:50]}...")
        
        # Create system prompt update message with original timestamp if available
        timestamp = message.created_at.isoformat() if hasattr(message, 'created_at') else datetime.datetime.now().isoformat()
        return create_system_update_message(prompt_text, timestamp)
        
    except Exception as e:
        logger.error(f"Error extracting prompt from update message: {e}")
        logger.debug(f"Update message content: {message.content}")
        return None

async def fetch_recent_messages(channel, limit=None):
    """
    Fetch recent messages from a Discord channel with optional limit.
    
    This is a utility function for fetching messages without the full processing
    pipeline, useful for lighter operations or testing.
    
    Args:
        channel: Discord channel object
        limit: Maximum number of messages to fetch (default: INITIAL_HISTORY_LOAD)
        
    Returns:
        list: List of Discord message objects (newest first)
        
    Raises:
        Exception: If Discord API call fails
    """
    if limit is None:
        limit = INITIAL_HISTORY_LOAD
    
    logger.debug(f"Fetching {limit} recent messages from #{channel.name}")
    
    messages = []
    try:
        async for message in channel.history(limit=limit):
            messages.append(message)
        
        logger.debug(f"Successfully fetched {len(messages)} messages")
        return messages
        
    except Exception as e:
        logger.error(f"Failed to fetch messages from #{channel.name}: {e}")
        raise

def count_processable_messages(messages, channel):
    """
    Count how many messages would be processed (not skipped) from a list.
    
    This utility function helps with planning and logging by counting how many
    messages would actually be added to history after filtering.
    
    Args:
        messages: List of Discord message objects
        channel: Discord channel object (for bot identity checking)
        
    Returns:
        tuple: (processable_count, skip_count, skip_reasons)
        
    Example:
        processable, skipped, reasons = count_processable_messages(messages, channel)
        logger.info(f"Would process {processable} messages, skip {skipped}")
    """
    processable_count = 0
    skip_count = 0
    skip_reasons = {}
    
    for message in messages:
        is_bot_message = message.author == channel.guild.me
        should_skip, skip_reason = should_skip_message_from_history(message, is_bot_message)
        
        if should_skip:
            skip_count += 1
            skip_reasons[skip_reason] = skip_reasons.get(skip_reason, 0) + 1
        else:
            processable_count += 1
    
    return processable_count, skip_count, skip_reasons
