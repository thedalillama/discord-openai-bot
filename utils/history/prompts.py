"""
System prompt and AI provider management for Discord bot.
"""
import datetime
from config import DEFAULT_SYSTEM_PROMPT
from utils.logging_utils import get_logger
from .storage import channel_system_prompts, channel_ai_providers, add_message_to_history, channel_history

logger = get_logger('history.prompts')

def get_system_prompt(channel_id):
    """
    Get the system prompt for a channel, falling back to default if none is set
    
    Args:
        channel_id: The Discord channel ID
        
    Returns:
        str: The system prompt to use for this channel
    """
    prompt = channel_system_prompts.get(channel_id, DEFAULT_SYSTEM_PROMPT)
    logger.debug(f"get_system_prompt for channel {channel_id}: {'custom prompt' if channel_id in channel_system_prompts else 'default prompt'}")
    return prompt

def set_system_prompt(channel_id, new_prompt):
    """
    Set a custom system prompt for a channel and record it in history
    
    Args:
        channel_id: The Discord channel ID
        new_prompt: The new system prompt to use
        
    Returns:
        bool: True if this is a change, False if same as before
    """
    logger.debug(f"set_system_prompt called for channel {channel_id}")
    logger.debug(f"new prompt: {new_prompt[:50]}...")
    
    current_prompt = get_system_prompt(channel_id)
    if current_prompt == new_prompt:
        logger.debug(f"Prompt unchanged (same as current)")
        return False
        
    # Store the prompt in the dictionary
    channel_system_prompts[channel_id] = new_prompt
    
    logger.debug(f"Updated prompt in channel_system_prompts dictionary")
    logger.debug(f"channel_system_prompts now has {len(channel_system_prompts)} entries")
    
    # Also add a special entry to the channel history to record this change
    if channel_id in channel_history:
        timestamp = datetime.datetime.now().isoformat()
        system_update_message = {
            "role": "system",
            "content": f"SYSTEM_PROMPT_UPDATE: {new_prompt}",
            "timestamp": timestamp
        }
        add_message_to_history(channel_id, system_update_message)
        
        logger.debug(f"Added system prompt update to channel history with timestamp {timestamp}")
        logger.debug(f"Channel history now has {len(channel_history[channel_id])} entries")
    else:
        logger.debug(f"Channel {channel_id} not in channel_history, skipping history update")
    
    return True

def get_ai_provider(channel_id):
    """
    Get the AI provider for a channel, returning None if no channel-specific setting
    
    Args:
        channel_id: The Discord channel ID
        
    Returns:
        str or None: The provider name for this channel, or None to use default
    """
    provider = channel_ai_providers.get(channel_id, None)
    logger.debug(f"get_ai_provider for channel {channel_id}: {'custom provider: ' + provider if provider else 'using default'}")
    return provider

def set_ai_provider(channel_id, provider_name):
    """
    Set a custom AI provider for a channel
    
    Args:
        channel_id: The Discord channel ID
        provider_name: The provider name (e.g., 'openai', 'anthropic')
        
    Returns:
        bool: True if this is a change, False if same as before
    """
    logger.debug(f"set_ai_provider called for channel {channel_id}")
    logger.debug(f"new provider: {provider_name}")
    
    current_provider = get_ai_provider(channel_id)
    if current_provider == provider_name:
        logger.debug(f"Provider unchanged (same as current)")
        return False
        
    # Store the provider in the dictionary
    channel_ai_providers[channel_id] = provider_name
    
    logger.debug(f"Updated provider in channel_ai_providers dictionary")
    logger.debug(f"channel_ai_providers now has {len(channel_ai_providers)} entries")
    
    return True

def remove_ai_provider(channel_id):
    """
    Remove custom AI provider for a channel (revert to default)
    
    Args:
        channel_id: The Discord channel ID
        
    Returns:
        str or None: The provider that was removed, or None if none was set
    """
    removed_provider = channel_ai_providers.pop(channel_id, None)
    if removed_provider:
        logger.debug(f"Removed custom AI provider for channel {channel_id}: {removed_provider}")
    return removed_provider

def remove_system_prompt(channel_id):
    """
    Remove custom system prompt for a channel (revert to default)
    
    Args:
        channel_id: The Discord channel ID
        
    Returns:
        str or None: The prompt that was removed, or None if none was set
    """
    removed_prompt = channel_system_prompts.pop(channel_id, None)
    if removed_prompt:
        logger.debug(f"Removed custom system prompt for channel {channel_id}")
        
        # Record the reset in history
        if channel_id in channel_history:
            timestamp = datetime.datetime.now().isoformat()
            reset_message = {
                "role": "system",
                "content": f"SYSTEM_PROMPT_UPDATE: {DEFAULT_SYSTEM_PROMPT}",
                "timestamp": timestamp
            }
            add_message_to_history(channel_id, reset_message)
            logger.debug(f"Added system prompt reset to history")
    
    return removed_prompt
